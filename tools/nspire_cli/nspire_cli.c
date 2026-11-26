// SPDX-License-Identifier: GPL-3.0-or-later (links libnspire; see COPYING in this folder)
/*
 * nspire-cli: a small command-line front end for libnspire (TI-Nspire USB link).
 *
 *   nspire-cli devices            list TI USB devices and whether they can be opened
 *   nspire-cli info               connect and print the handheld's name, OS and free space
 *   nspire-cli ls [PATH]          list a folder on the handheld ("/" = My Documents)
 *   nspire-cli mkdir PATH         create a folder (no error if it exists)
 *   nspire-cli put LOCAL REMOTE   upload a file, then read it back and compare
 *
 * Exit codes: 0 ok, 1 usage error, 2 no handheld found, 3 driver/open problem,
 *             4 link/protocol error, 5 verify failed, 6 local file error.
 *
 * Built by tools/build_tools.py against third_party/libnspire and third_party/libusb-*.
 * Because it links libnspire (GPL-3.0-or-later), the resulting nspire-cli.exe is
 * GPL-3.0-or-later too; this file is offered under the same licence.
 * Every line printed starts with a tag (OK/ERR/DEV/INFO/ITEM) so tools/send_to_calc.py
 * can parse it.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <libusb.h>

#include "nspire.h"

#define TI_VID 0x0451

static const char *model_for_pid(int pid) {
    switch (pid) {
        case 0xe012: return "TI-Nspire (CX / Clickpad / Touchpad)";
        case 0xe022: return "TI-Nspire CX II family";
        case 0xe003: case 0xe008: return "TI-84 Plus (not an Nspire)";
        case 0xe001: return "TI-GRAPH LINK USB cable";
        default: return "other TI device";
    }
}

static int cmd_devices(void) {
    libusb_context *ctx = NULL;
    libusb_device **list = NULL;
    int found = 0, usable = 0;
    if (libusb_init(&ctx) != 0) {
        printf("ERR libusb_init failed\n");
        return 3;
    }
    ssize_t n = libusb_get_device_list(ctx, &list);
    for (ssize_t i = 0; i < n; i++) {
        struct libusb_device_descriptor d;
        if (libusb_get_device_descriptor(list[i], &d) != 0) continue;
        if (d.idVendor != TI_VID) continue;
        found++;
        libusb_device_handle *h = NULL;
        int r = libusb_open(list[i], &h);
        const char *state;
        if (r == 0) {
            state = "ok";
            usable++;
            libusb_close(h);
        } else if (r == LIBUSB_ERROR_NOT_SUPPORTED) {
            state = "no-winusb-driver";
        } else if (r == LIBUSB_ERROR_ACCESS) {
            state = "busy-or-access-denied";
        } else {
            state = libusb_error_name(r);
        }
        printf("DEV vid=%04x pid=%04x bus=%d addr=%d model=\"%s\" open=%s\n", d.idVendor,
               d.idProduct, libusb_get_bus_number(list[i]), libusb_get_device_address(list[i]),
               model_for_pid(d.idProduct), state);
    }
    if (list) libusb_free_device_list(list, 1);
    libusb_exit(ctx);
    if (!found) {
        printf("ERR no TI device on USB\n");
        return 2;
    }
    if (!usable) {
        printf("ERR TI device found but it cannot be opened (driver)\n");
        return 3;
    }
    printf("OK %d device(s)\n", found);
    return 0;
}

static int open_handle(nspire_handle_t **h) {
    int r = nspire_init(h);
    if (r) {
        int e = -r;
        printf("ERR connect: %s (code %d)\n", nspire_strerror(r), e);
        if (e == NSPIRE_ERR_NODEVICE || e == NSPIRE_ERR_LIBUSB) return 2;
        return 4;
    }
    return 0;
}

static const char *hw_name(int t) {
    switch (t) {
        case NSPIRE_CAS: return "CAS";
        case NSPIRE_NONCAS: return "non-CAS";
        case NSPIRE_CASCX: return "CX CAS";
        case NSPIRE_NONCASCX: return "CX";
        default: return "unknown";
    }
}

static int cmd_info(void) {
    nspire_handle_t *h;
    int r = open_handle(&h);
    if (r) return r;
    struct nspire_devinfo i;
    memset(&i, 0, sizeof(i));
    r = nspire_device_info(h, &i);
    if (r) {
        printf("ERR device info: %s\n", nspire_strerror(r));
        nspire_free(h);
        return 4;
    }
    printf("INFO name=%.20s\n", i.device_name);
    printf("INFO id=%.28s\n", i.electronic_id);
    printf("INFO os=%u.%u.%u\n", i.versions[NSPIRE_VER_OS].major, i.versions[NSPIRE_VER_OS].minor,
           i.versions[NSPIRE_VER_OS].build);
    printf("INFO hw_type=0x%02x (%s)\n", (unsigned)i.hw_type, hw_name(i.hw_type));
    printf("INFO storage_free=%llu storage_total=%llu\n", (unsigned long long)i.storage.free,
           (unsigned long long)i.storage.total);
    printf("INFO battery=%s charging=%u\n",
           i.batt.status == NSPIRE_BATT_LOW ? "low"
           : i.batt.status == NSPIRE_BATT_OK ? "ok"
           : i.batt.status == NSPIRE_BATT_POWERED ? "powered" : "unknown",
           (unsigned)i.batt.is_charging);
    printf("INFO file_ext=%.8s\n", i.extensions.file);
    printf("OK\n");
    nspire_free(h);
    return 0;
}

static int cmd_ls(const char *path) {
    nspire_handle_t *h;
    int r = open_handle(&h);
    if (r) return r;
    struct nspire_dir_info *d = NULL;
    r = nspire_dirlist(h, path, &d);
    if (r) {
        printf("ERR ls %s: %s\n", path, nspire_strerror(r));
        nspire_free(h);
        return 4;
    }
    for (unsigned long k = 0; k < d->num; k++) {
        printf("ITEM %s %lu %s\n", d->items[k].type == NSPIRE_DIR ? "dir" : "file",
               d->items[k].size, d->items[k].name);
    }
    printf("OK %lu item(s)\n", d->num);
    nspire_dirlist_free(d);
    nspire_free(h);
    return 0;
}

static int cmd_mkdir(const char *path) {
    nspire_handle_t *h;
    int r = open_handle(&h);
    if (r) return r;
    struct nspire_dir_item it;
    if (nspire_attr(h, path, &it) == 0 && it.type == NSPIRE_DIR) {
        printf("OK exists %s\n", path);
        nspire_free(h);
        return 0;
    }
    r = nspire_dir_create(h, path);
    nspire_free(h);
    if (r) {
        printf("ERR mkdir %s: %s\n", path, nspire_strerror(r));
        return 4;
    }
    printf("OK created %s\n", path);
    return 0;
}

static int cmd_put(const char *local, const char *remote) {
    FILE *f = fopen(local, "rb");
    if (!f) {
        printf("ERR cannot open local file %s\n", local);
        return 6;
    }
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (size <= 0) {
        fclose(f);
        printf("ERR local file is empty: %s\n", local);
        return 6;
    }
    unsigned char *buf = malloc((size_t)size);
    unsigned char *back = malloc((size_t)size + 16);
    if (!buf || !back || fread(buf, 1, (size_t)size, f) != (size_t)size) {
        fclose(f);
        printf("ERR cannot read local file %s\n", local);
        return 6;
    }
    fclose(f);

    nspire_handle_t *h;
    int r = open_handle(&h);
    if (r) return r;
    r = nspire_file_write(h, remote, buf, (size_t)size);
    if (r) {
        printf("ERR upload %s: %s\n", remote, nspire_strerror(r));
        nspire_free(h);
        return 4;
    }
    printf("INFO sent %ld bytes to %s\n", size, remote);

    /* Check the size first: libnspire's file read does not bound its copy by the
       buffer size, so never read back more than we allocated. */
    struct nspire_dir_item it;
    r = nspire_attr(h, remote, &it);
    if (r) {
        printf("ERR verify: cannot stat %s: %s\n", remote, nspire_strerror(r));
        nspire_free(h);
        return 5;
    }
    if (it.size != (unsigned long)size) {
        printf("ERR verify: handheld has %lu bytes, expected %ld\n", it.size, size);
        nspire_free(h);
        return 5;
    }
    size_t got = 0;
    r = nspire_file_read(h, remote, back, (size_t)size + 16, &got);
    nspire_free(h);
    if (r) {
        printf("ERR read-back %s: %s\n", remote, nspire_strerror(r));
        return 5;
    }
    if (got != (size_t)size || memcmp(buf, back, (size_t)size) != 0) {
        printf("ERR verify: handheld has %lu bytes, expected %ld (or contents differ)\n",
               (unsigned long)got, size);
        return 5;
    }
    printf("OK verified %ld bytes at %s\n", size, remote);
    free(buf);
    free(back);
    return 0;
}

static int usage(void) {
    printf("usage: nspire-cli devices | info | ls [PATH] | mkdir PATH | put LOCAL REMOTE\n"
           "PATH is on the handheld; \"/\" is the top of My Documents.\n");
    return 1;
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc < 2) return usage();
    const char *c = argv[1];
    if (!strcmp(c, "devices")) return cmd_devices();
    if (!strcmp(c, "info")) return cmd_info();
    if (!strcmp(c, "ls")) return cmd_ls(argc > 2 ? argv[2] : "/");
    if (!strcmp(c, "mkdir") && argc == 3) return cmd_mkdir(argv[2]);
    if (!strcmp(c, "put") && argc == 4) return cmd_put(argv[2], argv[3]);
    return usage();
}
