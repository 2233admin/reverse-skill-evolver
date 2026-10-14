package com.burpmcp;

import burp.api.montoya.MontoyaApi;
import burp.api.montoya.http.Http;
import burp.api.montoya.http.handler.HttpHandler;
import burp.api.montoya.http.handler.HttpRequestToBeSent;
import burp.api.montoya.internal.MontoyaObjectFactory;
import burp.api.montoya.internal.ObjectFactoryLocator;
import com.google.gson.JsonObject;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

/** Actual server callbacks, with owned proxy fixtures and no Burp runtime or sockets. */
public final class McpHttpHandlerRaceTest {
    public static void main(String[] args) throws Exception {
        concurrentInstallClearingAndReconfiguration();
        failedInstallCanBeRetried();
        System.out.println("HTTP handler regressions passed: one concurrent callback, one edit/serialization, clear/reconfigure, failed-install retry");
    }

    private static void concurrentInstallClearingAndReconfiguration() throws Exception {
        List<HttpHandler> handlers = new CopyOnWriteArrayList<>();
        AtomicInteger installs = new AtomicInteger();
        CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1);
        Http http = fake(Http.class, (method, values) -> {
            if (!method.getName().equals("registerHttpHandler")) throw new AssertionError(method.getName());
            installs.incrementAndGet();
            handlers.add((HttpHandler) values[0]);
            entered.countDown();
            require(release.await(5, TimeUnit.SECONDS), "Registration fixture timed out");
            return null;
        });
        McpHttpServer server = server(http);
        JsonObject rules = rules();
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Runnable register = () -> {
            try { require(call(server, "registerHttpHandler", rules).has("success"), "Registration failed"); }
            catch (Throwable error) { failure.compareAndSet(null, error); }
        };
        Thread first = new Thread(register, "handler-first"), second = new Thread(register, "handler-second");
        first.start();
        try {
            require(entered.await(5, TimeUnit.SECONDS), "First registration never entered");
            second.start();
            long watchdog = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
            // Hold installation open until the second caller reaches the contested boundary.
            while (second.getState() != Thread.State.BLOCKED && installs.get() == 1
                    && second.isAlive() && System.nanoTime() < watchdog) Thread.onSpinWait();
            require(second.getState() == Thread.State.BLOCKED, "Concurrent caller bypassed the installation boundary");
            require(installs.get() == 1 && handlers.size() == 1, "Concurrent first calls installed duplicate callbacks");
        } finally {
            release.countDown();
            first.join(5000); second.join(5000);
            require(!first.isAlive() && !second.isAlive(), "Owned callers did not stop");
        }
        if (failure.get() != null) throw new AssertionError("Caller failed", failure.get());
        require(installs.get() == 1 && handlers.size() == 1, "First callers installed more than one callback");
        call(server, "registerHttpHandler", rules);
        assertWork(handlers, 1, 1);
        JsonObject cleared = call(server, "removeHttpHandler", new JsonObject());
        require(cleared.get("success").getAsBoolean() && cleared.get("message").getAsString().equals("Handler rules cleared"), "Clear envelope changed");
        assertWork(handlers, 0, 0);
        call(server, "registerHttpHandler", rules);
        assertWork(handlers, 1, 1);
        require(installs.get() == 1, "Clear/reconfigure reinstalled a callback");
    }

    private static void failedInstallCanBeRetried() throws Exception {
        AtomicInteger calls = new AtomicInteger();
        Http http = fake(Http.class, (method, values) -> {
            if (calls.incrementAndGet() == 1) throw new IllegalStateException("fixture registration failed");
            return null;
        });
        McpHttpServer server = server(http);
        require(call(server, "registerHttpHandler", rules()).get("error").getAsString().equals("fixture registration failed"), "Install error was hidden");
        require(call(server, "registerHttpHandler", rules()).get("success").getAsBoolean(), "Retry failed");
        call(server, "registerHttpHandler", rules());
        require(calls.get() == 2, "Active was published before success, or sequential registration duplicated callbacks");
    }

    private static void assertWork(List<HttpHandler> handlers, int expectedEdits, int expectedSerializations) {
        AtomicInteger edits = new AtomicInteger(), serializations = new AtomicInteger();
        AtomicReference<HttpRequestToBeSent> outgoing = new AtomicReference<>();
        outgoing.set(fake(HttpRequestToBeSent.class, (method, values) -> switch (method.getName()) {
            case "withAddedHeader" -> {
                require(values[0].equals("X-Fixture") && values[1].equals("value"), "Header pair changed");
                edits.incrementAndGet(); yield outgoing.get();
            }
            case "toString" -> { serializations.incrementAndGet(); yield "GET /a HTTP/1.1\r\nHost: fixture.invalid\r\n\r\n"; }
            default -> null;
        }));
        MontoyaObjectFactory previous = ObjectFactoryLocator.FACTORY;
        try {
            ObjectFactoryLocator.FACTORY = fake(MontoyaObjectFactory.class, (method, values) -> {
                if (method.getName().equals("httpRequest")) {
                    require(values[1].toString().contains("GET /aa HTTP/1.1"), "Replacement changed");
                    return outgoing.get();
                }
                return fake(method.getReturnType(), (m, v) -> null);
            });
            for (HttpHandler handler : handlers) handler.handleHttpRequestToBeSent(outgoing.get());
        } finally { ObjectFactoryLocator.FACTORY = previous; }
        require(edits.get() == expectedEdits && serializations.get() == expectedSerializations, "Request handled more than once or clear retained rules");
    }

    private static McpHttpServer server(Http http) {
        return new McpHttpServer(fake(MontoyaApi.class, (method, values) -> method.getName().equals("http") ? http : null), 0);
    }

    private static JsonObject rules() {
        JsonObject rules = new JsonObject();
        rules.addProperty("header_name", "X-Fixture"); rules.addProperty("header_value", "value");
        rules.addProperty("match", "a"); rules.addProperty("replace", "aa");
        return rules;
    }

    private static JsonObject call(McpHttpServer server, String name, JsonObject params) throws Exception {
        Method method = McpHttpServer.class.getDeclaredMethod(name, JsonObject.class);
        method.setAccessible(true);
        return (JsonObject) method.invoke(server, params);
    }

    private interface Answer { Object invoke(Method method, Object[] args) throws Throwable; }
    @SuppressWarnings("unchecked")
    private static <T> T fake(Class<T> type, Answer answer) {
        return (T) Proxy.newProxyInstance(type.getClassLoader(), new Class<?>[]{type}, (proxy, method, args) -> answer.invoke(method, args));
    }
    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
