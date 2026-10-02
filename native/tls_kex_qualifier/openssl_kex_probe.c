#include <openssl/core_dispatch.h>
#include <openssl/core_names.h>
#include <openssl/evp.h>
#include <openssl/opensslv.h>
#include <openssl/params.h>
#include <openssl/provider.h>
#include <stdio.h>
#include <string.h>

struct group_result { unsigned count, id, bits, is_kem; const char *name, *internal, *alg; };

static int group_cb(const OSSL_PARAM params[], void *arg) {
    struct group_result *r = arg;
    const OSSL_PARAM *p = OSSL_PARAM_locate_const(params, OSSL_CAPABILITY_TLS_GROUP_NAME);
    const char *name = NULL;
    if (p == NULL || !OSSL_PARAM_get_utf8_string_ptr(p, &name) || strcmp(name, "secp256r1") != 0)
        return 1;
    r->count++; r->name = name;
#define GETSTR(field, macro) do { p = OSSL_PARAM_locate_const(params, macro); if (p) OSSL_PARAM_get_utf8_string_ptr(p, &r->field); } while (0)
#define GETUINT(field, macro) do { p = OSSL_PARAM_locate_const(params, macro); if (p) OSSL_PARAM_get_uint(p, &r->field); } while (0)
    GETSTR(internal, OSSL_CAPABILITY_TLS_GROUP_NAME_INTERNAL);
    GETSTR(alg, OSSL_CAPABILITY_TLS_GROUP_ALG);
    GETUINT(id, OSSL_CAPABILITY_TLS_GROUP_ID);
    GETUINT(bits, OSSL_CAPABILITY_TLS_GROUP_SECURITY_BITS);
    GETUINT(is_kem, OSSL_CAPABILITY_TLS_GROUP_IS_KEM);
    return 1;
}

static const OSSL_ALGORITHM *find_algorithm(const OSSL_ALGORITHM *algs, const char *name) {
    for (; algs != NULL && algs->algorithm_names != NULL; algs++) {
        const char *start = algs->algorithm_names, *end;
        do {
            size_t segment_length;
            end = strchr(start, ':');
            segment_length = end == NULL ? strlen(start) : (size_t)(end - start);
            if (segment_length == strlen(name)
                    && strncmp(start, name, segment_length) == 0)
                return algs;
            start = end == NULL ? NULL : end + 1;
        } while (start != NULL);
    }
    return NULL;
}

static void print_ids(const OSSL_DISPATCH *d) {
    int comma = 0; putchar('[');
    for (; d != NULL && d->function_id != 0; d++) { printf("%s%d", comma ? "," : "", d->function_id); comma = 1; }
    putchar(']');
}

int main(void) {
    OSSL_LIB_CTX *ctx = OSSL_LIB_CTX_new();
    OSSL_PROVIDER *provider = NULL;
    struct group_result group = {0};
    const OSSL_ALGORITHM *kms, *kexs, *km, *kex;
    int km_no_store = -1, kex_no_store = -1;
    const char *opalg = NULL;
    if (ctx == NULL || (provider = OSSL_PROVIDER_load(ctx, "default")) == NULL) goto fail;
    if (!OSSL_PROVIDER_get_capabilities(provider, "TLS-GROUP", group_cb, &group)
            || group.count != 1 || group.alg == NULL) goto fail;
    kms = OSSL_PROVIDER_query_operation(provider, OSSL_OP_KEYMGMT, &km_no_store);
    km = find_algorithm(kms, group.alg); if (km == NULL) goto fail;
    for (const OSSL_DISPATCH *d = km->implementation; d->function_id != 0; d++)
        if (d->function_id == OSSL_FUNC_KEYMGMT_QUERY_OPERATION_NAME)
            opalg = OSSL_FUNC_keymgmt_query_operation_name(d)(OSSL_OP_KEYEXCH);
    if (opalg == NULL) opalg = group.alg;
    kexs = OSSL_PROVIDER_query_operation(provider, OSSL_OP_KEYEXCH, &kex_no_store);
    kex = find_algorithm(kexs, opalg); if (kex == NULL) goto fail;
    EVP_KEYEXCH *fetched = EVP_KEYEXCH_fetch(ctx, opalg, "provider=default");
    if (fetched == NULL || EVP_KEYEXCH_get0_provider(fetched) != provider) goto fail;
    printf("{\"openssl_identity\":\"%s\",\"private_libctx\":true,", OpenSSL_version(OPENSSL_VERSION));
    printf("\"property_query\":\"provider=default\",\"provider\":\"default\",");
    printf("\"group\":\"%s\",\"group_id\":%u,\"group_algorithm\":\"%s\",", group.name, group.id, group.alg);
    printf("\"operation_algorithm\":\"%s\",\"keymgmt_no_store\":%d,\"operation_no_store\":%d,", opalg, km_no_store, kex_no_store);
    printf("\"keymgmt_dispatch_ids\":"); print_ids(km->implementation);
    printf(",\"operation_dispatch_ids\":"); print_ids(kex->implementation); puts("}");
    EVP_KEYEXCH_free(fetched); OSSL_PROVIDER_unquery_operation(provider, OSSL_OP_KEYEXCH, kexs);
    OSSL_PROVIDER_unquery_operation(provider, OSSL_OP_KEYMGMT, kms); OSSL_PROVIDER_unload(provider); OSSL_LIB_CTX_free(ctx); return 0;
fail:
    fputs("strong qualification unsupported or ambiguous\n", stderr);
    if (provider != NULL)
        OSSL_PROVIDER_unload(provider);
    OSSL_LIB_CTX_free(ctx);
    return 2;
}
