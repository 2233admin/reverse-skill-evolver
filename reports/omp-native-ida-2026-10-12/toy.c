volatile unsigned char rse_unique[] = "RSE_IDA_LIVE_UNIQUE_20261012_C133";
volatile unsigned char rse_duplicate_a[] = "RSE_IDA_AMBIGUOUS_20261012";
volatile unsigned char rse_duplicate_b[] = "RSE_IDA_AMBIGUOUS_20261012";

__declspec(noinline) int validate_marker(const unsigned char *input) {
    for (unsigned int i = 0; i < sizeof(rse_unique) - 1; ++i)
        if (input[i] != rse_unique[i]) return 0;
    return 1;
}

int entry(void) {
    return validate_marker((const unsigned char *)rse_unique)
        + rse_duplicate_a[0] + rse_duplicate_b[0];
}
