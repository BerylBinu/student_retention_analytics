# Checks which AWS services this account is allowed to use.
# Creates tiny test resources and deletes them straight away. Costs nothing.

$ErrorActionPreference = "Continue"
$Region = "ap-southeast-2"
$Suffix = Get-Random -Maximum 999999
$Results = @()

function Test-Step($Name, [scriptblock]$Action) {
    $output = & $Action 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0) {
        $script:Results += [pscustomobject]@{ Check = $Name; Result = "ALLOWED"; Detail = "" }
    } else {
        $reason = "error"
        if ($output -match "service control policy") { $reason = "BLOCKED by organization (SCP)" }
        elseif ($output -match "AccessDenied|not authorized|UnauthorizedOperation") { $reason = "access denied" }
        $short = ($output -replace "\s+", " ").Trim()
        if ($short.Length -gt 160) { $short = $short.Substring(0, 160) + "..." }
        $script:Results += [pscustomobject]@{ Check = $Name; Result = $reason; Detail = $short }
    }
}

Write-Host "Checking permissions in $Region (about 30 seconds)..." -ForegroundColor Cyan

Test-Step "Lambda: list functions"        { aws lambda list-functions --max-items 1 --region $Region }
Test-Step "API Gateway: list HTTP APIs"   { aws apigatewayv2 get-apis --region $Region }
Test-Step "CloudWatch Logs: list"         { aws logs describe-log-groups --limit 1 --region $Region }
Test-Step "Secrets Manager: list"         { aws secretsmanager list-secrets --max-results 1 --region $Region }
Test-Step "IAM: list roles"               { aws iam list-roles --max-items 1 }

$Bucket = "perm-check-$Suffix-$Region"
Test-Step "S3: create bucket" { aws s3api create-bucket --bucket $Bucket --region $Region --create-bucket-configuration LocationConstraint=$Region }
aws s3api delete-bucket --bucket $Bucket --region $Region 2>$null | Out-Null

$Table = "perm-check-$Suffix"
Test-Step "DynamoDB: create table" { aws dynamodb create-table --table-name $Table --attribute-definitions AttributeName=id,AttributeType=S --key-schema AttributeName=id,KeyType=HASH --billing-mode PAY_PER_REQUEST --region $Region }
aws dynamodb wait table-exists --table-name $Table --region $Region 2>$null | Out-Null
aws dynamodb delete-table --table-name $Table --region $Region 2>$null | Out-Null

$QueueName = "perm-check-$Suffix"
Test-Step "SQS: create queue" { aws sqs create-queue --queue-name $QueueName --region $Region }
$QueueUrl = aws sqs get-queue-url --queue-name $QueueName --region $Region --query QueueUrl --output text 2>$null
if ($QueueUrl) { aws sqs delete-queue --queue-url $QueueUrl --region $Region 2>$null | Out-Null }

$TrustFile = Join-Path $env:TEMP "perm-check-trust.json"
'{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' | Set-Content -Path $TrustFile -Encoding ascii
$RoleName = "perm-check-$Suffix"
Test-Step "IAM: create role" { aws iam create-role --role-name $RoleName --assume-role-policy-document "file://$TrustFile" }
aws iam delete-role --role-name $RoleName 2>$null | Out-Null
Remove-Item $TrustFile -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Existing IAM roles in this account:" -ForegroundColor Cyan
aws iam list-roles --query "Roles[].RoleName" --output text 2>&1

Write-Host ""
Write-Host "RESULTS" -ForegroundColor Cyan
$Results | Format-Table -AutoSize -Wrap
Write-Host "Copy everything from 'Existing IAM roles' down and send it to Claude." -ForegroundColor Yellow