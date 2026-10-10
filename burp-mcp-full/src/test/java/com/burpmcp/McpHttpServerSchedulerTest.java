package com.burpmcp;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/** Dependency-free regression, run by Gradle's schedulerRegressionTest/check gate. */
public final class McpHttpServerSchedulerTest {
    private static final int WINDOW_SIZE = 50;
    private static final int WAIT_SECONDS = 10;

    public static void main(String[] args) throws Exception {
        replenishesWindowWhileFirstRequestIsBlocked();
        deadlineCancelsOutstandingWorkAndStopsSubmission();
    }

    private static void replenishesWindowWhileFirstRequestIsBlocked() throws Exception {
        CountDownLatch initialWindowStarted = new CountDownLatch(WINDOW_SIZE);
        CountDownLatch finishFastRequest = new CountDownLatch(1);
        CountDownLatch finishSlowRequests = new CountDownLatch(1);
        CountDownLatch successfulCandidate = new CountDownLatch(1);
        AtomicBoolean found = new AtomicBoolean(false);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peakActive = new AtomicInteger();
        AtomicInteger started = new AtomicInteger();
        ExecutorService coordinator = Executors.newSingleThreadExecutor();
        Future<Boolean> attack = coordinator.submit(() -> McpHttpServer.runBoundedAttack(
                0, WINDOW_SIZE, WINDOW_SIZE,
                System.nanoTime() + TimeUnit.SECONDS.toNanos(120), found,
                candidate -> () -> {
                    int inFlight = active.incrementAndGet();
                    peakActive.accumulateAndGet(inFlight, Math::max);
                    started.incrementAndGet();
                    try {
                        if (candidate < WINDOW_SIZE) {
                            initialWindowStarted.countDown();
                            // Only request 1 can complete before the test releases request 0.
                            if (candidate == 1) finishFastRequest.await();
                            else finishSlowRequests.await();
                        } else {
                            found.set(true);
                            successfulCandidate.countDown();
                        }
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    } finally {
                        active.decrementAndGet();
                    }
                }));
        try {
            require(initialWindowStarted.await(WAIT_SECONDS, TimeUnit.SECONDS),
                    "The initial 50-request window did not start");
            require(successfulCandidate.getCount() == 1,
                    "Candidate 50 started before any window slot was released");
            finishFastRequest.countDown();
            require(successfulCandidate.await(WAIT_SECONDS, TimeUnit.SECONDS),
                    "A completed later request did not replenish the window with candidate 50");
            require(finishSlowRequests.getCount() == 1,
                    "Request 0 must still be blocked when candidate 50 succeeds");
            require(found.get(), "The beyond-window candidate did not record a hit");
            require(!attack.isDone(), "An early hit must still drain outstanding requests");
            finishSlowRequests.countDown();
            require(!attack.get(WAIT_SECONDS, TimeUnit.SECONDS),
                    "The attack unexpectedly reported a timeout");
            require(started.get() == 51, "The complete range must execute exactly once");
            require(peakActive.get() <= WINDOW_SIZE, "The 50-task window was exceeded");
        } finally {
            finishFastRequest.countDown();
            finishSlowRequests.countDown();
            attack.cancel(true);
            coordinator.shutdownNow();
            require(coordinator.awaitTermination(WAIT_SECONDS, TimeUnit.SECONDS),
                    "The scheduler coordinator did not terminate");
        }
    }

    private static void deadlineCancelsOutstandingWorkAndStopsSubmission() throws Exception {
        CountDownLatch requestStarted = new CountDownLatch(1);
        CountDownLatch requestCancelled = new CountDownLatch(1);
        CountDownLatch releaseRequest = new CountDownLatch(1);
        AtomicInteger submitted = new AtomicInteger();
        ExecutorService coordinator = Executors.newSingleThreadExecutor();
        Future<Boolean> attack = coordinator.submit(() -> McpHttpServer.runBoundedAttack(
                0, 2, 1, System.nanoTime() + TimeUnit.SECONDS.toNanos(2),
                new AtomicBoolean(false),
                candidate -> {
                    submitted.incrementAndGet();
                    return () -> {
                        requestStarted.countDown();
                        try {
                            releaseRequest.await();
                        } catch (InterruptedException e) {
                            requestCancelled.countDown();
                            Thread.currentThread().interrupt();
                        }
                    };
                }));
        try {
            require(requestStarted.await(WAIT_SECONDS, TimeUnit.SECONDS),
                    "The first request did not start before its deadline");
            require(attack.get(WAIT_SECONDS, TimeUnit.SECONDS),
                    "An outstanding request at the deadline must report a timeout");
            require(requestCancelled.await(WAIT_SECONDS, TimeUnit.SECONDS),
                    "Deadline expiration must cancel the outstanding request");
            require(submitted.get() == 1,
                    "No later candidate may be submitted after deadline expiration");
        } finally {
            releaseRequest.countDown();
            attack.cancel(true);
            coordinator.shutdownNow();
            require(coordinator.awaitTermination(WAIT_SECONDS, TimeUnit.SECONDS),
                    "The deadline-test coordinator did not terminate");
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
