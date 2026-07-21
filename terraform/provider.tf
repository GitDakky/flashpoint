terraform {
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = ">= 0.69.0"
    }
  }
  required_version = ">= 1.5.0"
}

provider "proxmox" {
  # Set TF_VAR_proxmox_endpoint (e.g. https://pve.example.com:8006/) and
  # TF_VAR_proxmox_api_token in the environment.
  endpoint  = var.proxmox_endpoint
  api_token = var.proxmox_api_token
  insecure  = true

  ssh {
    agent    = false
    username = "root"
  }
}

variable "proxmox_endpoint" {
  description = "Proxmox API endpoint, e.g. https://pve.example.com:8006/"
  type        = string
}

variable "proxmox_api_token" {
  description = "Proxmox API token — set via TF_VAR_proxmox_api_token. Never commit."
  type        = string
  sensitive   = true
}
