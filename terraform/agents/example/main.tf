module "agent" {
  source     = "../../modules/agent"
  vmid       = var.vmid
  hostname   = var.hostname
  ip_address = var.ip_address
  tier       = var.tier
  mission    = var.mission
}

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
}
variable "mission" {
  type    = string
  default = ""
}

output "agent" {
  value     = module.agent
  sensitive = true
}
