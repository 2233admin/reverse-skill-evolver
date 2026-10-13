__declspec(dllimport) unsigned long __stdcall GetCurrentProcessId(void);
volatile char license_marker[] = "license-invalid-omp-owned-fixture-v2";
__declspec(dllexport) void *marker_reference = (void *)license_marker;
__declspec(dllexport) __declspec(noinline) int padding_function(int input) {
    volatile int value = input;
    for (int i = 0; i < 30; i++) value = value * 3 + i;
    return value;
}
__declspec(dllexport) __declspec(noinline) int check_license(int input) {
    return input + license_marker[0] + (int)(GetCurrentProcessId() & 7) + 1;
}
__declspec(dllexport) __declspec(noinline) int decode_payload(int input) {
    return check_license(input) ^ 0x66;
}
