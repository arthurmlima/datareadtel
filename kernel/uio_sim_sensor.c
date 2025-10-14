
// uio_sim_sensor.c - RAM-backed UIO device exposing a 4KB register block
#include <linux/module.h>
#include <linux/uio_driver.h>
#include <linux/slab.h>
#include <linux/types.h>

#define DRV_NAME "uio_sim_sensor"
#define MMIO_SIZE 4096

static struct uio_info sim_uio;
static void *mmio;

static irqreturn_t sim_handler(int irq, struct uio_info *info) {
    return IRQ_NONE;
}

static int __init sim_init(void) {
    mmio = kzalloc(MMIO_SIZE, GFP_KERNEL);
    if (!mmio) return -ENOMEM;

    // Basic header
    *(u32 *)(mmio + 0x000) = 0x53554D31; // MAGIC
    *(u32 *)(mmio + 0x004) = 0x00010000; // VERSION
    *(u32 *)(mmio + 0x008) = 0x1;        // STATUS OK

    sim_uio.name = DRV_NAME;
    sim_uio.version = "1.0";
    sim_uio.irq = UIO_IRQ_NONE;
    sim_uio.handler = sim_handler;

    sim_uio.mem[0].addr = (phys_addr_t)(uintptr_t)mmio; // logical addr
    sim_uio.mem[0].size = MMIO_SIZE;
    sim_uio.mem[0].memtype = UIO_MEM_LOGICAL;

    if (uio_register_device(NULL, &sim_uio)) {
        kfree(mmio);
        pr_err(DRV_NAME ": register failed\n");
        return -ENODEV;
    }

    pr_info(DRV_NAME ": registered /dev/uio0 size=%d\n", MMIO_SIZE);
    return 0;
}

static void __exit sim_exit(void) {
    uio_unregister_device(&sim_uio);
    kfree(mmio);
    pr_info(DRV_NAME ": unloaded\n");
}

MODULE_AUTHOR("Arthur & ChatGPT");
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("UIO RAM-backed fake sensor MMIO");
module_init(sim_init);
module_exit(sim_exit);
