__declspec(dllimport) unsigned long __stdcall GetCurrentProcessId(void);
volatile char license_marker[] = "license-invalid-omp-owned-fixture";
__declspec(dllexport) void *marker_reference = (void *)license_marker;
__declspec(dllexport) __declspec(noinline) int verify_license(int input) {
    return input + license_marker[0] + (int)(GetCurrentProcessId() & 7);
}
__declspec(dllexport) __declspec(noinline) int decode_payload(int input) {
    return verify_license(input) ^ 0x55;
}
