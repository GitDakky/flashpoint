output "vmid"        { value = proxmox_virtual_environment_container.agent.vm_id }
output "hostname"    { value = var.hostname }
output "ip_address"  { value = var.ip_address }
output "tier"        { value = var.tier }
output "gateway_url" { value = "http://${var.ip_address}:18789" }
output "ssh_command" { value = "ssh -J root@${var.bastion_host} root@${var.ip_address}" }
