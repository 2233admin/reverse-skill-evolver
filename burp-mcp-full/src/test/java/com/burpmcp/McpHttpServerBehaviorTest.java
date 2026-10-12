package com.burpmcp;

import burp.api.montoya.MontoyaApi;
import burp.api.montoya.internal.MontoyaObjectFactory;
import burp.api.montoya.internal.ObjectFactoryLocator;
import burp.api.montoya.http.Http;
import burp.api.montoya.http.RequestOptions;
import burp.api.montoya.http.message.requests.HttpRequest;
import burp.api.montoya.proxy.ProxyHttpRequestResponse;
import com.google.gson.*;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

/** No Burp runtime or network: exercise pagination, serialization and bounded attack work. */
public final class McpHttpServerBehaviorTest {
    /** Run pagination, regex, serialization, and sequential attack regressions. */
    public static void main(String[] args) throws Exception {
        paginationPreservesFilteredIndicesAndBoundaries();
        technologyNamesAreLiteralAndCaseInsensitive();
        numericRequestsReuseHeadersWithoutChangingWireFormat();
        sequentialRequestUsesExplicitTimeoutOptions();
        stalledCallbackCannotHoldAttackCoordinatorPastDeadline();
        sequentialRequestsReturnValuesAndPropagateFailures();
        expiredDeadlineNeverSubmits();
        interruptionCancelsPendingRequestAndStopsSubmission();
        deadlineCancelsPendingRequestAndStopsSubmission();
        callerRegexesAcceptLinearPatternsAndRejectUnsupportedSyntax();
        sequentialAttackErrorAndCountContractsRemainIntact();
        sequentialAttackSuccessAndExtractionContractsRemainIntact();
    }

    /** Verify newest-first pagination, filtered indices, totals, and legacy boundary behavior. */
    private static void paginationPreservesFilteredIndicesAndBoundaries() throws Exception {
        List<ProxyHttpRequestResponse> history = List.of(
                entry("GET", "https://a/old", 200), entry("POST", "https://a/post", 201),
                entry("GET", "https://b/middle", 404), entry("GET", "https://a/new", 200));
        MontoyaApi api = fake(MontoyaApi.class, (method, args) -> {
            if (method.getName().equals("proxy")) return fake(method.getReturnType(),
                    (m, a) -> m.getName().equals("history") ? history : null);
            throw new AssertionError(method.getName());
        });
        McpHttpServer server = new McpHttpServer(api, 0);
        JsonObject page = history(server, "{\"limit\":2,\"offset\":1}");
        require(page.get("total").getAsInt() == 4, "Unfiltered total changed");
        require(page.getAsJsonArray("items").get(0).getAsJsonObject().get("url").getAsString().equals("https://b/middle"), "Newest-first ordering changed");
        require(page.getAsJsonArray("items").get(1).getAsJsonObject().get("index").getAsInt() == 2, "Page index changed");
        page = history(server, "{\"limit\":1,\"offset\":1,\"url_filter\":\"https://a\",\"method_filter\":\"get\",\"status_filter\":200}");
        JsonObject item = page.getAsJsonArray("items").get(0).getAsJsonObject();
        require(page.get("total").getAsInt() == 2 && item.get("index").getAsInt() == 1, "Filtered total/index changed");
        require(item.get("url").getAsString().equals("https://a/old") && item.get("status").getAsInt() == 200 && item.get("length").getAsInt() == 3, "Filtered row values changed");
        require(history(server, "{\"offset\":4}").getAsJsonArray("items").isEmpty(), "Offset at end must be empty");
        require(history(server, "{\"offset\":100}").getAsJsonArray("items").isEmpty(), "Offset past end must be empty");
        require(history(server, "{\"limit\":2147483647,\"offset\":1}").getAsJsonArray("items").isEmpty(), "Integer page-end overflow contract changed");
        try { history(server, "{\"offset\":-1}"); throw new AssertionError("Negative offset stopped failing"); }
        catch (java.lang.reflect.InvocationTargetException e) {
            require(e.getCause() instanceof IndexOutOfBoundsException, "Negative offset failure changed");
        }
        page = history(server, "{\"limit\":0}");
        require(page.get("total").getAsInt() == 4 && page.getAsJsonArray("items").isEmpty(), "Zero page size must retain total");
        page = history(server, "{\"url_filter\":\"missing\"}");
        require(page.get("total").getAsInt() == 0 && page.getAsJsonArray("items").isEmpty(), "Empty filter result changed");
    }

    /** Invoke the private history operation with parsed JSON parameters for assertions. */
    private static JsonObject history(McpHttpServer server, String json) throws Exception {
        Method method = McpHttpServer.class.getDeclaredMethod("proxyHistory", JsonObject.class);
        method.setAccessible(true);
        return (JsonObject) method.invoke(server, JsonParser.parseString(json).getAsJsonObject());
    }

    /** Create a proxy history fixture with the requested method, URL, status, and a fixed body length. */
    private static ProxyHttpRequestResponse entry(String verb, String url, int status) {
        HttpRequest request = fake(HttpRequest.class, (m, a) -> switch (m.getName()) {
            case "method" -> verb;
            case "url" -> url;
            case "toString" -> url;
            default -> throw new AssertionError(m.getName());
        });
        return fake(ProxyHttpRequestResponse.class, (m, a) -> switch (m.getName()) {
            case "finalRequest" -> request;
            case "response" -> fake(m.getReturnType(), (r, b) -> switch (r.getName()) {
                case "statusCode" -> {
                    if (r.getReturnType() == short.class) yield (short) status;
                    yield status;
                }
                case "bodyToString", "toString" -> url;
                case "body" -> fake(r.getReturnType(), (body, ignored) -> {
                    if (body.getName().equals("length")) return 3;
                    throw new AssertionError(body.getName());
                });
                default -> throw new AssertionError(r.getName());
            });
            default -> throw new AssertionError(m.getName());
        });
    }

    /** Verify RE2J matching semantics and consistent error envelopes for unsupported caller patterns. */
    private static void callerRegexesAcceptLinearPatternsAndRejectUnsupportedSyntax() throws Exception {
        List<ProxyHttpRequestResponse> entries = new ArrayList<>();
        entries.add(entry("GET", "Token:abc Token:DEF", 200));
        MontoyaApi api = fake(MontoyaApi.class, (method, args) -> {
            if (method.getName().equals("proxy")) return fake(method.getReturnType(),
                    (m, a) -> m.getName().equals("history") ? entries : null);
            throw new AssertionError(method.getName());
        });
        McpHttpServer server = new McpHttpServer(api, 0);
        for (String field : List.of("url", "request", "response")) {
            JsonObject search = new JsonObject();
            search.addProperty("regex", "token:[a-z]+");
            search.addProperty("search_in", field);
            JsonObject result = call(server, "searchHistory", search);
            require(result.get("matches").getAsInt() == 1 && result.getAsJsonArray("items").get(0).getAsJsonObject().get("index").getAsInt() == 0,
                    "Search find/case-insensitive/index contract changed for " + field);
        }
        JsonObject extract = new JsonObject();
        extract.addProperty("index", 0);
        extract.addProperty("regex", "Token:([a-z]+)");
        JsonObject result = call(server, "extractFromResponse", extract);
        require(result.get("total_matches").getAsInt() == 1
                && result.getAsJsonArray("matches").get(0).getAsString().equals("Token:abc"), "Extraction must remain case-sensitive and return group zero");
        extract.addProperty("regex", "");
        require(call(server, "extractFromResponse", extract).get("total_matches").getAsInt() == 20, "Zero-width find progression changed");
        entries.set(0, entry("GET", "a".repeat(100000) + "!", 200));
        extract.addProperty("regex", "(a+)+$");
        require(call(server, "extractFromResponse", extract).get("total_matches").getAsInt() == 0, "Nested repetition nonmatch changed");
        JsonObject search = new JsonObject();
        search.addProperty("regex", "(a+)+$");
        require(call(server, "searchHistory", search).get("matches").getAsInt() == 0, "Nested repetition search nonmatch changed");
        JsonObject options = new JsonObject();
        options.addProperty("url_template", "https://example.invalid/@@");
        options.addProperty("from", 1);
        options.addProperty("to", 0);
        options.addProperty("grep_extract", "Token:([a-z]+)");
        result = call(server, "intruderWithOptions", options);
        require(result.get("total_requests").getAsInt() == 0 && result.get("errors").getAsInt() == 0
                && result.getAsJsonArray("hit_details").isEmpty(), "Valid grep pattern changed the empty-attack envelope");
        for (String unsupported : List.of("(a)\\1", "(?=a)", "(?!a)", "(?<=a)", "(?<!a)", "(?>a)", "a++", "[")) {
            search.addProperty("regex", unsupported);
            extract.addProperty("regex", unsupported);
            options.addProperty("grep_extract", unsupported);
            for (JsonObject error : List.of(call(server, "searchHistory", search),
                    call(server, "extractFromResponse", extract), call(server, "intruderWithOptions", options))) {
                require(error.size() == 1 && error.get("error").getAsString().startsWith("Invalid or unsupported RE2J regex:"),
                        "Unsupported syntax must use the operation error envelope: " + unsupported);
            }
        }
    }

    /** Invoke a private JSON operation by name, exposing reflection failures to the test. */
    private static JsonObject call(McpHttpServer server, String operation, JsonObject params) throws Exception {
        Method method = McpHttpServer.class.getDeclaredMethod(operation, JsonObject.class);
        method.setAccessible(true);
        return (JsonObject) method.invoke(server, params);
    }

    /** Verify invalid candidates preserve each sequential attack operation's error and request counts. */
    private static void sequentialAttackErrorAndCountContractsRemainIntact() throws Exception {
        McpHttpServer server = new McpHttpServer(fake(MontoyaApi.class, (m, a) -> {
            throw new AssertionError("Invalid candidates must not invoke Montoya: " + m.getName());
        }), 0);
        for (String operation : List.of("intruderAttack", "intruderAttackWordlist", "intruderPitchfork",
                "intruderClusterBomb", "intruderBatteringRam", "intruderWithOptions")) {
            JsonObject params = JsonParser.parseString("{\"url_template\":\"://@@\",\"from\":0,\"to\":2,\"wordlist\":[\"0\",\"1\",\"2\"],\"placeholders\":{\"@@\":[\"0\",\"1\",\"2\"]},\"max_requests\":3}").getAsJsonObject();
            JsonObject result = call(server, operation, params);
            require(result.get("errors").getAsInt() == 3, "Candidate errors changed for " + operation);
            require(result.get("total_requests").getAsInt() == (operation.equals("intruderClusterBomb") ? 3 : 0),
                    "Attempt/success count contract changed for " + operation);
            require(result.get("hits").getAsInt() == 0 && result.getAsJsonArray("hit_details").isEmpty(),
                    "Failed candidates must not become hits for " + operation);
        }
    }

    private static void sequentialAttackSuccessAndExtractionContractsRemainIntact() throws Exception {
        AtomicInteger sends = new AtomicInteger();
        MontoyaObjectFactory previousFactory = ObjectFactoryLocator.FACTORY;
        ObjectFactoryLocator.FACTORY = fake(MontoyaObjectFactory.class, (method, args) ->
                fake(method.getReturnType(), (m, a) -> {
                    if (m.getName().equals("withResponseTimeout")) {
                        require((Long) a[0] > 0, "Attack response timeout must be positive");
                        return fake(RequestOptions.class, (ignored, values) -> null);
                    }
                    return null;
                }));
        try {
            Http http = fake(Http.class, (method, args) -> {
                require(method.getName().equals("sendRequest") && args.length == 2,
                        "Attack must send with explicit response options");
                sends.incrementAndGet();
                return fake(method.getReturnType(), (m, a) ->
                        m.getName().equals("response") ? entry("GET", "Token:abc", 200).response() : null);
            });
            McpHttpServer server = new McpHttpServer(fake(MontoyaApi.class, (m, a) ->
                    m.getName().equals("http") ? http : null), 0);
            for (String operation : List.of("intruderAttack", "intruderAttackWordlist", "intruderPitchfork",
                    "intruderClusterBomb", "intruderBatteringRam", "intruderWithOptions")) {
                sends.set(0);
                JsonObject params = JsonParser.parseString("{\"url_template\":\"https://example.invalid/@@\",\"from\":0,\"to\":2,\"wordlist\":[\"0\",\"1\",\"2\"],\"placeholders\":{\"@@\":[\"0\",\"1\",\"2\"]},\"max_requests\":3,\"success_length_not\":99,\"grep_extract\":\"Token:[a-z]+\"}").getAsJsonObject();
                JsonObject result = call(server, operation, params);
                require(!result.has("error"), "Successful attack failed for " + operation + ": " + result);
                require(result.get("total_requests").getAsInt() == 3 && sends.get() == 3,
                        "Successful request count changed for " + operation);
                require(result.get("errors").getAsInt() == 0 && result.get("hits").getAsInt() == 3,
                        "Successful hit count changed for " + operation);
                for (JsonElement row : result.getAsJsonArray("hit_details")) {
                    JsonObject hit = row.getAsJsonObject();
                    require(hit.get("length").getAsInt() == 3,
                            "Successful response details changed for " + operation);
                    if (operation.equals("intruderPitchfork"))
                        require(hit.has("iteration") && !hit.has("status"), "Pitchfork hit shape changed");
                    else
                        require(hit.get("status").getAsInt() == 200, "Successful response status changed for " + operation);
                    if (operation.equals("intruderWithOptions"))
                        require(hit.get("extracted").getAsString().equals("Token:abc"), "Grep extraction lost the full match");
                }
            }
        } finally {
            ObjectFactoryLocator.FACTORY = previousFactory;
        }
    }

    /** Verify only complete supported header names match, regardless of case. */
    private static void technologyNamesAreLiteralAndCaseInsensitive() {
        for (String name : List.of("server", "SeRvEr", "X-POWERED-BY", "x-AspNet-Version"))
            require(McpHttpServer.isTechnologyHeader(name), "Technology header excluded: " + name);
        for (String name : List.of("servers", "server-extra", "x-powered-by ", "content-type", ""))
            require(!McpHttpServer.isTechnologyHeader(name), "Non-technology header included: " + name);
    }

    /** Verify header values are converted once and request text retains its existing wire format. */
    private static void numericRequestsReuseHeadersWithoutChangingWireFormat() {
        AtomicInteger conversions = new AtomicInteger();
        JsonObject headers = new JsonObject();
        headers.add("X-Test", new JsonElement() {
            /** Count header value conversions and return a literal placeholder-bearing value. */
            @Override public String getAsString() { conversions.incrementAndGet(); return "static @@"; }
            /** Return this immutable test value without allocating a copy. */
            @Override public JsonElement deepCopy() { return this; }
        });
        headers.addProperty("Host", "override.example");
        String block = McpHttpServer.renderHeaderLines(headers);
        require(McpHttpServer.numericAttackRequest("POST", "/001?q=%2f", "a", block, "é001")
                .equals("POST /001?q=%2f HTTP/1.1\r\nHost: a\r\nX-Test: static @@\r\nHost: override.example\r\nContent-Length: 4\r\n\r\né001"), "Body/header wire format changed");
        require(McpHttpServer.numericAttackRequest("GET", "/002", "b", block, "")
                .equals("GET /002 HTTP/1.1\r\nHost: b\r\nX-Test: static @@\r\nHost: override.example\r\n\r\n"), "Empty-body wire format changed");
        require(conversions.get() == 1, "Invariant values must be converted once, without payload substitution");
    }

    /** Verify sequential sends use Montoya request options with the remaining response timeout. */
    private static void sequentialRequestUsesExplicitTimeoutOptions() throws Exception {
        long[] timeout = {0};
        RequestOptions[] options = new RequestOptions[1];
        options[0] = fake(RequestOptions.class, (method, args) -> {
            require(method.getName().equals("withResponseTimeout"), "Response timeout setter was not called");
            timeout[0] = (Long) args[0];
            return options[0];
        });
        MontoyaObjectFactory previousFactory = ObjectFactoryLocator.FACTORY;
        ObjectFactoryLocator.FACTORY = fake(MontoyaObjectFactory.class,
                (method, args) -> method.getName().equals("requestOptions") ? options[0] : null);
        AtomicInteger requests = new AtomicInteger();
        try {
            Http http = fake(Http.class, (method, args) -> {
                require(method.getName().equals("sendRequest"), "Sequential attack used a non-request operation");
                require(args != null && args.length == 2 && args[1] == options[0],
                        "Sequential attack must use Montoya's explicit request-options overload");
                requests.incrementAndGet();
                return null;
            });
            HttpRequest request = fake(HttpRequest.class, (method, args) -> null);
            try (var attack = new McpHttpServer.SequentialAttack(
                    new JsonObject(), System.nanoTime() + TimeUnit.SECONDS.toNanos(5))) {
                attack.send(http, request);
            }
        } finally {
            ObjectFactoryLocator.FACTORY = previousFactory;
        }
        require(requests.get() == 1, "Sequential request did not reach the explicit timeout overload once");
        require(timeout[0] > 0 && timeout[0] <= 5000, "Request timeout did not use remaining attack time");
    }

    /** Verify the coordinator exits on deadline even when a callback ignores interruption. */
    private static void stalledCallbackCannotHoldAttackCoordinatorPastDeadline() throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        JsonObject result = new JsonObject();
        AtomicInteger submissions = new AtomicInteger();
        ExecutorService coordinator = Executors.newSingleThreadExecutor();
        Future<?> run = coordinator.submit(() -> {
            try (var attack = new McpHttpServer.SequentialAttack(
                    result, System.nanoTime() + TimeUnit.SECONDS.toNanos(1))) {
                try {
                    attack.send(timeout -> {
                        submissions.incrementAndGet();
                        started.countDown();
                        while (true) {
                            try { release.await(); break; }
                            catch (InterruptedException ignored) { }
                        }
                        finished.countDown();
                        return "late response";
                    });
                    throw new AssertionError("Deadline failed to release the attack coordinator");
                } catch (TimeoutException expected) {
                    require(result.get("timed_out").getAsBoolean(), "Stalled call lost timeout status");
                    try {
                        attack.send(timeout -> { submissions.incrementAndGet(); return "too late"; });
                        throw new AssertionError("A later candidate was submitted after the deadline");
                    } catch (TimeoutException expectedAgain) {
                    } catch (Exception e) {
                        throw new AssertionError(e);
                    }
                } catch (Exception e) {
                    throw new AssertionError(e);
                }
            }
        });
        try {
            require(started.await(3, TimeUnit.SECONDS), "Stalled callback never started");
            run.get(3, TimeUnit.SECONDS);
            require(finished.getCount() == 1, "Non-cooperative callback unexpectedly finished before release");
            require(submissions.get() == 1, "A candidate was submitted after the deadline");
        } finally {
            release.countDown();
            coordinator.shutdownNow();
            require(finished.await(3, TimeUnit.SECONDS), "Stalled callback did not exit after release");
            require(coordinator.awaitTermination(3, TimeUnit.SECONDS), "Coordinator did not terminate");
        }
    }

    /** Verify values and callback failures propagate while later requests remain eligible. */
    private static void sequentialRequestsReturnValuesAndPropagateFailures() throws Exception {
        JsonObject result = new JsonObject();
        try (var attack = new McpHttpServer.SequentialAttack(result, System.nanoTime() + TimeUnit.SECONDS.toNanos(10))) {
            require(attack.send(timeout -> { require(timeout > 0 && timeout <= 10000, "Response timeout must use remaining time"); return "hit"; }).equals("hit"), "Successful response lost");
            try { attack.send(timeout -> { throw new IllegalStateException("failure"); }); throw new AssertionError("Failure swallowed"); }
            catch (IllegalStateException expected) { require(expected.getMessage().equals("failure"), "Failure changed"); }
            require(attack.canContinue(), "Individual failure must not stop subsequent requests");
            require(attack.send(timeout -> "next").equals("next"), "Next response lost");
        }
        require(!result.has("timed_out") && !result.has("interrupted"), "Successful attack acquired cancellation flags");
    }

    /** Verify an already expired attack records timeout without submitting a callback. */
    private static void expiredDeadlineNeverSubmits() throws Exception {
        AtomicInteger submitted = new AtomicInteger();
        JsonObject result = new JsonObject();
        try (var attack = new McpHttpServer.SequentialAttack(result, System.nanoTime() - 1)) {
            require(!attack.canContinue(), "Expired attack continued");
            try { attack.send(timeout -> submitted.incrementAndGet()); throw new AssertionError("Expired send succeeded"); }
            catch (TimeoutException expected) { }
        }
        require(submitted.get() == 0 && result.get("timed_out").getAsBoolean(), "Expired attack submitted work or lost timeout flag");
    }

    /** Verify coordinator interruption cancels pending work and prevents further submission. */
    private static void interruptionCancelsPendingRequestAndStopsSubmission() throws Exception {
        exerciseCancellation(true);
    }

    /** Verify deadline expiry cancels pending work and prevents further submission. */
    private static void deadlineCancelsPendingRequestAndStopsSubmission() throws Exception {
        exerciseCancellation(false);
    }

    /** Exercise interruption or deadline cancellation using a blocked request and verify cleanup. */
    private static void exerciseCancellation(boolean interrupt) throws Exception {
        CountDownLatch started = new CountDownLatch(1), cancelled = new CountDownLatch(1), release = new CountDownLatch(1);
        AtomicInteger submitted = new AtomicInteger();
        JsonObject result = new JsonObject();
        ExecutorService coordinator = Executors.newSingleThreadExecutor();
        Future<?> run = coordinator.submit(() -> {
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(interrupt ? 30 : 2);
            try (var attack = new McpHttpServer.SequentialAttack(result, deadline)) {
                try {
                    attack.send(timeout -> {
                        submitted.incrementAndGet(); started.countDown();
                        try { release.await(); }
                        catch (InterruptedException e) { cancelled.countDown(); Thread.currentThread().interrupt(); }
                        return "response";
                    });
                    throw new AssertionError("Pending work escaped cancellation");
                } catch (InterruptedException e) {
                    require(interrupt && Thread.currentThread().isInterrupted(), "Interrupt status was not preserved");
                } catch (TimeoutException e) {
                    require(!interrupt, "Interruption misreported as timeout");
                }
                require(!attack.canContinue(), "Cancelled attack continued");
            } catch (Exception e) { throw new AssertionError(e); }
        });
        try {
            require(started.await(10, TimeUnit.SECONDS), "Request never started");
            if (interrupt) coordinator.shutdownNow();
            run.get(10, TimeUnit.SECONDS);
            require(cancelled.await(10, TimeUnit.SECONDS), "Pending request was not interrupted");
            require(submitted.get() == 1 && result.get(interrupt ? "interrupted" : "timed_out").getAsBoolean(), "Cancellation status/submissions changed");
        } finally {
            release.countDown(); run.cancel(true); coordinator.shutdownNow();
            require(coordinator.awaitTermination(10, TimeUnit.SECONDS), "Coordinator did not terminate");
        }
    }

    private interface Answer {
        /** Handle a reflected interface call for a synthetic Montoya test object. */
        Object invoke(Method method, Object[] args) throws Throwable;
    }
    /** Create an interface proxy that delegates each invocation to the supplied test answer. */
    @SuppressWarnings("unchecked")
    private static <T> T fake(Class<T> type, Answer answer) {
        return (T) Proxy.newProxyInstance(type.getClassLoader(), new Class<?>[]{type},
                (proxy, method, args) -> answer.invoke(method, args));
    }
    /** Throw AssertionError with the supplied message when a test condition is false. */
    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
