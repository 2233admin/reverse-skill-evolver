#!/bin/bash
# BurpSuite MCP Full Control - Linux/macOS Build Script
# Requires: JDK 21+, curl
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" && pwd

if [ -n "$JAVA_HOME" ]; then
    JAVAC="$JAVA_HOME/bin/javac"
    JAR="$JAVA_HOME/bin/jar"
else
    JAVAC="$(command -v javac || true)"
    JAR="$(command -v jar || true)"
fi
SRC="src/main/java/com/burpmcp"
LIB="lib"
OUT="build/classes"
DIST="build/libs"
ARTIFACT="$DIST/burp-mcp-full.jar"

echo "[1/4] Downloading dependencies..."
mkdir -p "$LIB"
download_dependency() {
    local name="$1" url="$2"
    if [ ! -s "$LIB/$name.jar" ]; then
        if ! curl -fsSL -o "$LIB/$name.jar.tmp" "$url"; then
            rm -f "$LIB/$name.jar.tmp"
            echo "ERROR: Could not download $name." >&2
            return 1
        fi
        [ -s "$LIB/$name.jar.tmp" ] || { rm -f "$LIB/$name.jar.tmp"; echo "ERROR: Empty $name download." >&2; return 1; }
        mv "$LIB/$name.jar.tmp" "$LIB/$name.jar"
    fi
    [ -s "$LIB/$name.jar" ]
}
download_dependency montoya-api "https://repo1.maven.org/maven2/net/portswigger/burp/extensions/montoya-api/2025.5/montoya-api-2025.5.jar"
download_dependency gson "https://repo1.maven.org/maven2/com/google/code/gson/gson/2.11.0/gson-2.11.0.jar"
download_dependency nanohttpd "https://repo1.maven.org/maven2/org/nanohttpd/nanohttpd/2.3.1/nanohttpd-2.3.1.jar"
download_dependency re2j "https://repo1.maven.org/maven2/com/google/re2j/re2j/1.8/re2j-1.8.jar"

# A failed input scan or an equal timestamp must rebuild, never claim freshness.
fresh=false
inputs="$(mktemp)"
trap 'rm -f "$inputs"' EXIT
if [ -s "$ARTIFACT" ] && find src "$LIB" -type f \( -name '*.java' -o -name '*.jar' \) -print0 > "$inputs"; then
    fresh=true
    while IFS= read -r -d '' input; do
        if [ ! "$ARTIFACT" -nt "$input" ]; then fresh=false; break; fi
    done < "$inputs"
    [ "$ARTIFACT" -nt "$SCRIPT_DIR/build.sh" ] && [ "$ARTIFACT" -nt "$SCRIPT_DIR/build.bat" ] || fresh=false
fi
if [ "$fresh" = true ]; then
    echo "[2/4] Compilation skipped (JAR is newer than all inputs)."
    echo "[3/4] Packaging skipped."
else
    if [ -z "$JAVAC" ] || [ ! -x "$JAVAC" ]; then
        echo "ERROR: Install JDK 21+ or set JAVA_HOME." >&2
        exit 1
    fi
    if [ -z "$JAR" ] || [ ! -x "$JAR" ]; then
        echo "ERROR: jar not found. Install JDK 21+." >&2
        exit 1
    fi
    echo "[2/4] Compiling..."
    mkdir -p "$OUT"
    "$JAVAC" -cp "$LIB/montoya-api.jar:$LIB/gson.jar:$LIB/nanohttpd.jar:$LIB/re2j.jar" -d "$OUT" "$SRC"/*.java

    echo "[3/4] Packaging fat jar..."
    mkdir -p "$DIST"
    cd "$OUT" && pwd
    "$JAR" xf "../../$LIB/gson.jar" com
    "$JAR" xf "../../$LIB/nanohttpd.jar" fi
    "$JAR" xf "../../$LIB/re2j.jar" com
    cd "$SCRIPT_DIR" && pwd
    "$JAR" cf "$ARTIFACT" -C "$OUT" .
fi

echo "[4/4] Done!"
echo "Output: $ARTIFACT"
echo ""
echo "Install: Burp Suite -> Extensions -> Add -> Java -> Select $ARTIFACT"
echo ""
echo "MCP config (any client):"
printf '  { "command": "node", "args": ["%s/mcp-bridge.js"] }\n' "$SCRIPT_DIR"
