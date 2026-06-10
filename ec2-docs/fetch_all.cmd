@echo off
REM ============================================================================
REM  fetch_all.cmd - Download EC2 config, relationships and AMIs as JSON
REM  Windows Command Prompt (cmd.exe). AWS CLI v2 (tested 2.34.x).
REM
REM  Usage:   fetch_all.cmd [region] [profile]
REM  Example: fetch_all.cmd us-east-1 myprofile
REM
REM  One command -> one JSON file in .\json\. A matching Python formatter in
REM  .\format\ turns each file into Markdown.
REM
REM  Windows quoting note: cmd.exe uses double quotes " " around values. The
REM  --query / --filters strings below contain no spaces or embedded JSON, so
REM  no escaping is required.
REM ============================================================================

setlocal

set "REGION=%~1"
if "%REGION%"=="" set "REGION=us-east-1"

set "PROFILE_ARG="
if not "%~2"=="" set "PROFILE_ARG=--profile %~2"

set "OUT=json"
if not exist "%OUT%" mkdir "%OUT%"

set "COMMON=--region %REGION% %PROFILE_ARG% --output json"

echo Region: %REGION%   Output folder: %OUT%
echo.
echo === Core instance config and relationships ===

echo  - instances.json
aws ec2 describe-instances %COMMON% > "%OUT%\instances.json"

echo  - instance_status.json
aws ec2 describe-instance-status --include-all-instances %COMMON% > "%OUT%\instance_status.json"

echo  - iam_instance_profiles.json
aws ec2 describe-iam-instance-profile-associations %COMMON% > "%OUT%\iam_instance_profiles.json"

echo  - security_groups.json
aws ec2 describe-security-groups %COMMON% > "%OUT%\security_groups.json"

echo  - security_group_rules.json
aws ec2 describe-security-group-rules %COMMON% > "%OUT%\security_group_rules.json"

echo  - network_interfaces.json
aws ec2 describe-network-interfaces %COMMON% > "%OUT%\network_interfaces.json"

echo  - volumes.json
aws ec2 describe-volumes %COMMON% > "%OUT%\volumes.json"

echo  - subnets.json
aws ec2 describe-subnets %COMMON% > "%OUT%\subnets.json"

echo  - vpcs.json
aws ec2 describe-vpcs %COMMON% > "%OUT%\vpcs.json"

echo  - key_pairs.json
aws ec2 describe-key-pairs %COMMON% > "%OUT%\key_pairs.json"

echo  - tags.json
aws ec2 describe-tags %COMMON% > "%OUT%\tags.json"

echo.
echo === AMIs ===

echo  - images_self.json
aws ec2 describe-images --owners self %COMMON% > "%OUT%\images_self.json"

echo  - images_in_use.json  (AMIs referenced by your instances)
REM Collect the distinct AMI ids in use, then describe just those.
set "IMG_IDS="
for /f "usebackq delims=" %%I in (`aws ec2 describe-instances --region %REGION% %PROFILE_ARG% --query "Reservations[].Instances[].ImageId" --output text`) do set "IMG_IDS=%%I"
if not "%IMG_IDS%"=="" (
    aws ec2 describe-images --image-ids %IMG_IDS% %COMMON% > "%OUT%\images_in_use.json"
) else (
    echo {"Images": []} > "%OUT%\images_in_use.json"
)

echo.
echo === IAM role permissions for instance roles ===
echo  - role_permissions.json
python fetch_role_permissions.py "%OUT%" "%REGION%" "%~2"

echo.
echo Done. JSON written to %OUT%\
endlocal
