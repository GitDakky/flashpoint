variable "vmid" {
  type = number
}

variable "hostname" {
  type = string
}

variable "ip_address" {
  type = string
}

variable "tier" {
  type    = string
  default = "ephemeral"
  validation {
    condition     = contains(["ephemeral", "standard", "heavy"], var.tier)
    error_message = "tier must be ephemeral, standard, or heavy"
  }
}

variable "mission" {
  type    = string
  default = ""
}

variable "proxmox_node" {
  type    = string
  default = "proxmox"
}

variable "template_vmid" {
  type    = number
  default = 8000
}

variable "gateway_ip" {
  type    = string
  default = "10.0.0.1"
}

variable "nameserver" {
  type    = string
  default = "8.8.8.8"
}

variable "decisions_db_host" {
  type    = string
  default = ""   # decisions DB host — set in terraform.tfvars (not committed)
}

variable "decisions_db_pass" {
  description = "agent_writer password — set via TF_VAR_decisions_db_pass"
  type        = string
  sensitive   = true
}

variable "bastion_host" {
  description = "SSH bastion host used to reach agents on the internal bridge"
  type        = string
  default     = ""
}

variable "ssh_private_key_path" {
  description = "Path to the SSH private key for agent/bastion access"
  type        = string
  default     = "~/.ssh/id_ed25519"
}

locals {
  tier_config = {
    ephemeral = { cores = 1, memory = 2048, disk = "10" }
    standard  = { cores = 2, memory = 4096, disk = "20" }
    heavy     = { cores = 4, memory = 8192, disk = "40" }
  }
  config = local.tier_config[var.tier]
}
