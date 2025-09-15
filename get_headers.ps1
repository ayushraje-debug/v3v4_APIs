# Mandatory: change this variable to match your target Prism Central
$pc_ip = "10.38.81.7"

# Mandatory: change this variable to match existing VM in the Prism Central
$target_vm_name = "ubuntu-server"

# Optional: change these variables if needed
$new_name = "renamed_vm_with_v4_APIs"
$new_description = "Updated Description with v4 APIs"

Write-Host "[ACTION] Starting script to rename VM [$($target_vm_name)] to new name [$($new_name)]" -ForegroundColor Cyan

# Prism Central credential
$pc_cred = Get-Credential -Message "Please enter an account with API access to Prism Central"

# Setup default headers
$default_headers = New-Object "System.Collections.Generic.Dictionary[[String],[String]]"
$default_headers.Add("Accept", "application/json")
$default_headers.Add("Content-Type", "application/json")

# Convert Prism Central credential to base64 authorization header and add to $default_headers
$bytes = [System.Text.Encoding]::UTF8.GetBytes("$($pc_cred.UserName):$($pc_cred.GetNetworkCredential().Password)")
$base64 = [Convert]::ToBase64String($bytes)
$default_headers['Authorization'] = "Basic " + $base64