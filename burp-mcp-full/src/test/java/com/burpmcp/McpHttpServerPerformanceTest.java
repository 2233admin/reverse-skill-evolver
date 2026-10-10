package com.burpmcp;

import burp.api.montoya.MontoyaApi;
import burp.api.montoya.core.ByteArray;
import burp.api.montoya.http.message.requests.HttpRequest;
import burp.api.montoya.http.message.responses.HttpResponse;
import burp.api.montoya.proxy.ProxyHttpRequestResponse;
import burp.api.montoya.proxy.ProxyWebSocketMessage;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;
import java.util.concurrent.atomic.AtomicInteger;

/** Plain Java regression, run by Gradle's performanceRegressionTest/check gate. */
public final class McpHttpServerPerformanceTest {
    public static void main(String[] args) throws Exception {
        historyCountsAllMatchesButSerializesOnlyThePage();
        regexToolsPreserveResultsAndRejectUnsupportedSyntax();
        previewsPreserveDecodedCharactersWithoutConvertingWholePayloads();
        webSocketPreviewUsesOneBoundedConversion();
        invariantHeaderPatternMatchesWholeNames();
    }

    private static void historyCountsAllMatchesButSerializesOnlyThePage() throws Exception {
        AtomicInteger serializedBodies = new AtomicInteger();
        AtomicInteger previousCalls = new AtomicInteger();
        List<ProxyHttpRequestResponse> history = new LinkedList<>() {
            @Override public ProxyHttpRequestResponse get(int index) {
                throw new AssertionError("History pagination must not perform indexed traversal");
            }

            @SuppressWarnings("unchecked")
            @Override public ListIterator<ProxyHttpRequestResponse> listIterator(int index) {
                ListIterator<ProxyHttpRequestResponse> delegate = super.listIterator(index);
                return (ListIterator<ProxyHttpRequestResponse>) Proxy.newProxyInstance(
                        ListIterator.class.getClassLoader(),
                        new Class<?>[] {ListIterator.class},
                        (proxy, method, args) -> {
                            if (method.getName().equals("previous")) previousCalls.incrementAndGet();
                            try {
                                return method.invoke(delegate, args);
                            } catch (InvocationTargetException exception) {
                                throw exception.getCause();
                            }
                        });
            }
        };
        history.add(entry("GET", "https://keep/0", 200, "zero", serializedBodies));
        history.add(entry("POST", "https://keep/1", 201, "one", serializedBodies));
        history.add(entry("get", "https://keep/2", 200, "two", serializedBodies));
        history.add(entry("GET", "https://skip/3", 200, "three", serializedBodies));
        history.add(entry("GET", "https://keep/4", 0, null, serializedBodies));
        history.add(entry("GET", "https://keep/5", 200, "five", serializedBodies));
        McpHttpServer server = server(history, List.of());
        JsonObject params = json("{\"url_filter\":\"keep\",\"method_filter\":\"GET\",\"status_filter\":200,\"offset\":1,\"limit\":1}");
        JsonObject result = call(server, "proxy_history", params);
        require(result.get("total").getAsInt() == 3, "Total must count beyond the retained page");
        JsonArray items = result.getAsJsonArray("items");
        require(items.size() == 1, "Only the requested page may be serialized");
        JsonObject item = items.get(0).getAsJsonObject();
        require(item.get("index").getAsInt() == 1, "Index is the reverse filtered ordinal, not raw history index");
        require(item.get("url").getAsString().equals("https://keep/2"), "Filtered newest-first order changed");
        require(item.get("length").getAsInt() == 3 && item.get("status").getAsInt() == 200, "History schema changed");
        require(serializedBodies.get() == 1, "Off-page bodies must not be serialized");
        for (String page : List.of("{\"offset\":99,\"limit\":2}", "{\"limit\":0}", "{\"offset\":2147483647,\"limit\":2147483647}")) {
            result = call(server, "proxy_history", json(page));
            require(result.get("total").getAsInt() == 6 && result.getAsJsonArray("items").isEmpty(), "Empty page must retain exact total");
        }
        require(serializedBodies.get() == 1, "Empty pages must not serialize entries");
        previousCalls.set(0);
        result = call(server, "proxy_history", json("{\"offset\":1,\"limit\":2147483647}"));
        items = result.getAsJsonArray("items");
        require(items.size() == 5, "A large valid limit must return the full remaining page");
        require(items.get(0).getAsJsonObject().get("index").getAsInt() == 1, "Large-limit offset changed");
        require(items.get(4).getAsJsonObject().get("index").getAsInt() == 5, "Large-limit page end changed");
        require(previousCalls.get() == 5, "Large-limit paging must visit only the available page");
        try {
            call(server, "proxy_history", json("{\"offset\":-1,\"limit\":0}"));
            throw new AssertionError("Negative offsets must fail even when limit is zero");
        } catch (InvocationTargetException exception) {
            require(exception.getCause() instanceof IndexOutOfBoundsException, "Negative offset error changed");
        }
        result = call(server(List.of(), List.of()), "proxy_history", new JsonObject());
        require(result.get("total").getAsInt() == 0 && result.getAsJsonArray("items").isEmpty(), "Empty history changed");
    }

    private static void regexToolsPreserveResultsAndRejectUnsupportedSyntax() throws Exception {
        McpHttpServer server = server(List.of(
                entry("GET", "https://example/old", 200, "id=12 id=34", new AtomicInteger()),
                entry("POST", "https://example/NEW", 200, "second", new AtomicInteger())), List.of());
        JsonObject result = call(server, "search_history", json("{\"regex\":\"example/(new|old)\",\"limit\":1}"));
        require(result.get("matches").getAsInt() == 1, "Search limit or case-insensitive matching changed");
        require(result.getAsJsonArray("items").get(0).getAsJsonObject().get("index").getAsInt() == 1, "Search must return raw newest-first index");
        result = call(server, "search_history", json("{\"regex\":\"request-token\",\"search_in\":\"request\"}"));
        require(result.get("matches").getAsInt() == 2, "Request search changed");
        result = call(server, "search_history", json("{\"regex\":\"id=\\\\d+\",\"search_in\":\"response\"}"));
        require(result.get("matches").getAsInt() == 1, "Response search changed");
        JsonObject extraction = new JsonObject();
        extraction.addProperty("index", 0);
        extraction.addProperty("regex", "id=(\\d+)");
        result = call(server, "extract_from_response", extraction);
        require(result.get("total_matches").getAsInt() == 2, "Extraction count changed");
        require(result.getAsJsonArray("matches").toString().equals("[\"id=12\",\"id=34\"]"), "Extraction must return full matches in order");
        extraction.addProperty("regex", "ID=\\d+");
        require(call(server, "extract_from_response", extraction).get("total_matches").getAsInt() == 0, "Extraction must remain case-sensitive");
        for (String regex : List.of("[", "(a)\\1", "(?=a)", "(?<=a)b", "(?>a)", "a++")) {
            extraction.addProperty("regex", regex);
            for (String tool : List.of("search_history", "extract_from_response")) {
                result = call(server, tool, extraction);
                require(result.has("error") && !result.has("matches"), "Unsupported regex must return a client error for " + tool + ": " + regex);
            }
        }
        McpHttpServer adversarial = server(List.of(entry("GET", "a".repeat(100000) + "!", 200, "", new AtomicInteger())), List.of());
        require(call(adversarial, "search_history", json("{\"regex\":\"(a+)+$\"}")).get("matches").getAsInt() == 0,
                "Nested repetition must safely return no match, not backtrack");
    }

    private static void previewsPreserveDecodedCharactersWithoutConvertingWholePayloads() throws Exception {
        for (String text : List.of("", "plain", "中😀é".repeat(30000))) {
            for (int limit : new int[] {0, 1, 2, 3, 4, 7, 300, 500, 10000, 50000}) {
                AtomicInteger maxPrefix = new AtomicInteger();
                ByteArray bytes = bytes(text.getBytes(StandardCharsets.UTF_8), maxPrefix, false);
                String actual = McpHttpServer.preview(bytes, limit);
                require(actual.equals(text.substring(0, Math.min(limit, text.length()))), "Preview changed decoded characters at " + limit);
                require(maxPrefix.get() <= Math.min(bytes.length(), 4L * (limit + 1)), "Preview converted beyond its bounded character prefix");
            }
        }
        byte[] binary = new byte[] {65, (byte) 0xff, (byte) 0xc3, (byte) 0xa9, 66};
        String decoded = new String(binary, StandardCharsets.UTF_8);
        require(McpHttpServer.preview(bytes(binary, new AtomicInteger(), false), 3).equals(decoded.substring(0, 3)), "Invalid byte decoding changed");
        Method truncated = McpHttpServer.class.getDeclaredMethod("truncatedPreview", ByteArray.class, int.class);
        truncated.setAccessible(true);
        for (String text : List.of("abc", "abcd", "abcde")) {
            String expected = text.length() > 4 ? "abcd...[truncated]" : text;
            require(truncated.invoke(null, bytes(text.getBytes(StandardCharsets.UTF_8), new AtomicInteger(), false), 4).equals(expected), "Truncation marker changed");
        }
    }

    private static void webSocketPreviewUsesOneBoundedConversion() throws Exception {
        AtomicInteger maxPrefix = new AtomicInteger();
        AtomicInteger payloadReads = new AtomicInteger();
        ProxyWebSocketMessage message = mock(ProxyWebSocketMessage.class, (proxy, method, args) -> {
            if (method.getName().equals("direction")) return method.getReturnType().getEnumConstants()[0];
            if (method.getName().equals("payload")) {
                payloadReads.incrementAndGet();
                return bytes("x".repeat(1000000).getBytes(StandardCharsets.UTF_8), maxPrefix, false);
            }
            throw new AssertionError(method);
        });
        JsonObject result = call(server(List.of(), List.of(message)), "proxy_websocket", new JsonObject());
        require(result.get("total").getAsInt() == 1, "WebSocket result schema changed");
        require(result.getAsJsonArray("messages").get(0).getAsJsonObject().get("payload").getAsString().equals("x".repeat(500)), "WebSocket preview changed");
        require(payloadReads.get() == 1 && maxPrefix.get() == 501, "WebSocket payload must use one bounded conversion");
    }

    private static void invariantHeaderPatternMatchesWholeNames() throws Exception {
        var field = McpHttpServer.class.getDeclaredField("TECHNOLOGY_HEADER_PATTERN");
        field.setAccessible(true);
        var pattern = (java.util.regex.Pattern) field.get(null);
        for (String name : List.of("server", "x-powered-by", "x-aspnet-version")) require(pattern.matcher(name).matches(), "Technology header lost");
        require(!pattern.matcher("server-extra").matches(), "Technology headers must match the entire name");
    }

    private static ProxyHttpRequestResponse entry(String verb, String url, int status, String text, AtomicInteger serializedBodies) {
        HttpRequest request = mock(HttpRequest.class, (proxy, method, args) -> switch (method.getName()) {
            case "url" -> url;
            case "method" -> verb;
            case "toString" -> url + " request-token";
            default -> throw new AssertionError(method);
        });
        HttpResponse response = text == null ? null : mock(HttpResponse.class, (proxy, method, args) -> switch (method.getName()) {
            case "statusCode" -> (short) status;
            case "bodyToString", "toString" -> text;
            case "body" -> {
                serializedBodies.incrementAndGet();
                yield bytes(text.getBytes(StandardCharsets.UTF_8), new AtomicInteger(), false);
            }
            default -> throw new AssertionError(method);
        });
        return mock(ProxyHttpRequestResponse.class, (proxy, method, args) -> switch (method.getName()) {
            case "finalRequest" -> request;
            case "response" -> response;
            default -> throw new AssertionError(method);
        });
    }

    private static ByteArray bytes(byte[] data, AtomicInteger maxPrefix, boolean slice) {
        return mock(ByteArray.class, (proxy, method, args) -> switch (method.getName()) {
            case "length" -> data.length;
            case "subArray" -> {
                int start = (int) args[0], end = (int) args[1];
                require(start == 0 && end <= data.length, "Preview slice must be a valid byte prefix");
                maxPrefix.accumulateAndGet(end, Math::max);
                yield bytes(java.util.Arrays.copyOfRange(data, start, end), maxPrefix, true);
            }
            case "toString" -> {
                require(slice, "Whole payload conversion is forbidden for a preview");
                yield new String(data, StandardCharsets.UTF_8);
            }
            default -> throw new AssertionError(method);
        });
    }

    private static McpHttpServer server(List<ProxyHttpRequestResponse> history, List<ProxyWebSocketMessage> messages) {
        MontoyaApi api = mock(MontoyaApi.class, (proxy, method, args) -> {
            if (!method.getName().equals("proxy")) throw new AssertionError(method);
            return mock(method.getReturnType(), (p, m, a) -> switch (m.getName()) {
                case "history" -> history;
                case "webSocketHistory" -> messages;
                default -> throw new AssertionError(m);
            });
        });
        return new McpHttpServer(api, 0);
    }

    private static JsonObject call(McpHttpServer server, String tool, JsonObject params) throws Exception {
        Method dispatch = McpHttpServer.class.getDeclaredMethod("dispatch", String.class, JsonObject.class);
        dispatch.setAccessible(true);
        return (JsonObject) dispatch.invoke(server, tool, params);
    }

    private static <T> T mock(Class<T> type, InvocationHandler handler) {
        return type.cast(Proxy.newProxyInstance(type.getClassLoader(), new Class<?>[] {type}, handler));
    }

    private static JsonObject json(String value) {
        return JsonParser.parseString(value).getAsJsonObject();
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
