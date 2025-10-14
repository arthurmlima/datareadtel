
// Minimal reader: mmap and print some values once per 100ms.
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>

#define PAGE 4096
#define ACCEL_X 0x010
#define ACCEL_Y 0x014
#define ACCEL_Z 0x018
#define AIRSPEED 0x050

static inline float r32(void *base, off_t off) {
    return *(volatile float *)((uint8_t*)base + off);
}

int main(int argc, char **argv) {
    const char *path = "/dev/uio0";
    if (argc > 1) path = argv[1];

    int fd = open(path, O_RDONLY);
    if (fd < 0) { perror("open"); return 1; }

    void *regs = mmap(NULL, PAGE, PROT_READ, MAP_SHARED, fd, 0);
    if (regs == MAP_FAILED) { perror("mmap"); return 1; }

    for (int i=0; i<20; ++i) {
        float ax = r32(regs, ACCEL_X);
        float ay = r32(regs, ACCEL_Y);
        float az = r32(regs, ACCEL_Z);
        float v = r32(regs, AIRSPEED);
        printf("ACCEL: %+.3f %+.3f %+.3f  V=%.2f\n", ax, ay, az, v);
        usleep(100000);
    }

    munmap(regs, PAGE);
    close(fd);
    return 0;
}
