# Fingerprinting Tool

This tool analyzes delivery reciept timings in end-to-end encrypted messaging applications to infer user activity. By sending specially crafted messages that reference non-existent message IDs, the tool can silently determine whether a device is online or offline based on the timing of delivery receipts. This method exploits insufficient server-side validation and can also be used to trigger resource-intensive operations on the target device, potentially leading to denial-of-service conditions.

> [!CAUTION]
> Use this tool responsibly and only on systems you own or have explicit permission to test.
