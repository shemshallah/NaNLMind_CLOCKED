#ifndef CLOCKED_NAN_H
#define CLOCKED_NAN_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Four legal NaN16 head classes. */
typedef enum {
    CLOCKED_NAN_SIGNAL_POSITIVE = 0,
    CLOCKED_NAN_SIGNAL_NEGATIVE = 1,
    CLOCKED_NAN_QUIET_POSITIVE  = 2,
    CLOCKED_NAN_QUIET_NEGATIVE  = 3
} clocked_nan_type;

typedef struct {
    uint64_t raw;
} clocked_nan16;

/* Hardware-neutral architecture identity used by build receipts. */
const char *clocked_arch_name(void);
const char *clocked_arch_endianness(void);
int clocked_arch_is_little_endian(void);

/* Raw NaN16 word: far head BE, payload LE, near head LE. */
clocked_nan16 clocked_nan16_make(clocked_nan_type far_type,
                                clocked_nan_type near_type,
                                uint32_t payload);
uint16_t clocked_nan16_far_head(clocked_nan16 word);
uint16_t clocked_nan16_near_head(clocked_nan16 word);
uint8_t clocked_nan16_opcode(clocked_nan16 word);
uint32_t clocked_nan16_payload(clocked_nan16 word);
int clocked_nan16_valid(clocked_nan16 word);

/* Canonical raw byte order is independent of host endianness. */
int clocked_nan16_to_bytes(clocked_nan16 word, uint8_t out[8]);
int clocked_nan16_from_bytes(const uint8_t in[8], clocked_nan16 *out);

/* Five-part route bytes: HW slot, BS0, MC0, SC0, GM0, terminator. */
int clocked_nan16_route_bytes(uint8_t hw_slot, uint8_t out[6]);
int clocked_nan16_route_text(uint8_t hw_slot, char *out, size_t capacity);

/* NANNET login request body for /v1/bootstrap/oidc. Caller supplies HTTP. */
int clocked_nannet_login_body(const char *id_token, uint8_t slot,
                              char *out, size_t capacity);
int clocked_nannet_auth_header(const char *bearer_token,
                               char *out, size_t capacity);

/* NaN16 Boolean evaluation, matching NaNLMind's 32-lane table. */
uint32_t clocked_nan16_eval_bool(uint8_t opcode, uint32_t a, uint32_t b);

#ifdef __cplusplus
}
#endif

#endif
