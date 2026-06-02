#!/bin/bash
# Setup script for the APSystems reverse-engineering lab
# Run inside the Lima VM after docker compose is up
set -euo pipefail

REDROID_HOST="localhost:5555"
MITMPROXY_HOST="localhost:8080"
APK_FILE="${APK_FILE:-apsystems-ema.apk}"

echo "=== Waiting for Redroid to boot ==="
for i in $(seq 1 60); do
    if adb connect "$REDROID_HOST" 2>/dev/null && adb -s "$REDROID_HOST" shell getprop sys.boot_completed 2>/dev/null | grep -q 1; then
        echo "Redroid is ready!"
        break
    fi
    echo "Waiting... ($i/60)"
    sleep 5
done

if ! adb -s "$REDROID_HOST" shell getprop sys.boot_completed 2>/dev/null | grep -q 1; then
    echo "ERROR: Redroid failed to boot"
    exit 1
fi

echo ""
echo "=== Setting up mitmproxy CA certificate ==="
# Copy the mitmproxy CA cert from the mitmproxy container
CA_CERT="/tmp/mitmproxy-ca-cert.pem"
docker cp mitmproxy:/home/mitmproxy/.mitmproxy/mitmproxy-ca-cert.pem "$CA_CERT" 2>/dev/null || {
    echo "Generating CA cert by making a test request..."
    curl -s -o /dev/null -k -x "http://$MITMPROXY_HOST" "https://www.google.com" || true
    sleep 2
    docker cp mitmproxy:/home/mitmproxy/.mitmproxy/mitmproxy-ca-cert.pem "$CA_CERT"
}

# Push CA cert to Android system store (requires root, redroid is rooted)
adb -s "$REDROID_HOST" push "$CA_CERT" /sdcard/Download/mitmproxy-ca-cert.pem
adb -s "$REDROID_HOST" shell su -c "
    cp /sdcard/Download/mitmproxy-ca-cert.pem /system/etc/security/cacerts/$(openssl x509 -inform PEM -subject_hash_old -in /dev/stdin -noout 2>/dev/null || echo 'c8750f0d').0
" 2>/dev/null || {
    # Alternative: install as user cert
    adb -s "$REDROID_HOST" shell am start -a android.intent.action.VIEW -d file:///sdcard/Download/mitmproxy-ca-cert.pem -t application/x-x509-ca-cert
    echo "Please accept the certificate installation on the device"
    sleep 5
}

echo ""
echo "=== Setting up HTTP proxy ==="
# Get the mitmproxy container IP on the Docker network
MITM_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' mitmproxy)
echo "mitmproxy IP: $MITM_IP"

# Set proxy via Android settings
adb -s "$REDROID_HOST" shell settings put global http_proxy "$MITM_IP:8080"

echo ""
echo "=== Installing APSystems EMA APK ==="
if [ -f "$APK_FILE" ]; then
    adb -s "$REDROID_HOST" install -r "$APK_FILE"
    echo "APK installed!"
else
    echo "APK file '$APK_FILE' not found."
    echo "Download it from the Google Play Store or your device and place it as '$APK_FILE' in this directory."
    echo "Then run: adb -s $REDROID_HOST install -r $APK_FILE"
fi

echo ""
echo "=== Setup complete ==="
echo "1. Launch the APSystems EMA app: adb -s $REDROID_HOST shell am start -n com.apsemaappforandroid/.ui.activity.SplashActivity"
echo "2. Log in with your credentials"
echo "3. Navigate to the battery/storage screen"
echo "4. Traffic is being captured to ./capture/"
echo "5. Watch live: docker logs -f mitmproxy"
echo "6. When done, analyze: python3 analyze-captures.py ./capture/"
