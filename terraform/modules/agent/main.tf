resource "proxmox_virtual_environment_container" "agent" {
  node_name   = var.proxmox_node
  vm_id       = var.vmid
  description = "AS agent | tier:${var.tier} | mission:${var.mission}"
  started     = true

  clone {
    vm_id     = var.template_vmid
    node_name = var.proxmox_node
  }

  initialization {
    hostname = var.hostname
    ip_config {
      ipv4 {
        address = "${var.ip_address}/24"
        gateway = var.gateway_ip
      }
    }
    dns {
      server = var.nameserver
    }
  }

  cpu {
    cores = local.config.cores
  }

  memory {
    dedicated = local.config.memory
    swap      = 512
  }

  disk {
    datastore_id = "local-lvm"
    size         = local.config.disk
  }

  network_interface {
    name   = "eth0"
    bridge = "internal"
  }

  provisioner "remote-exec" {
    connection {
      type        = "ssh"
      host        = var.ip_address
      user        = "root"
      private_key = file(var.ssh_private_key_path)
      timeout     = "3m"
      bastion_host        = var.bastion_host
      bastion_user        = "root"
      bastion_private_key = file(var.ssh_private_key_path)
    }
    inline = [
      "mkdir -p /root/clawd",
      "printf 'AS_AGENT_ID=ct-${var.vmid}\\nAS_AGENT_VMID=${var.vmid}\\nAS_AGENT_TIER=${var.tier}\\nAS_DECISIONS_HOST=${var.decisions_db_host}\\nAS_DECISIONS_PASS=${var.decisions_db_pass}\\n' >> /root/clawd/.env",
      "loginctl enable-linger root 2>/dev/null || true",
      "XDG_RUNTIME_DIR=/run/user/0 openclaw gateway restart 2>/dev/null || true",
      "echo Agent ${var.hostname} ready"
    ]
  }
}
