# (SO9169)
# Before starting deployment process please update the following variables.
# ENV - unique variable that indicates the environment name. Global resources created, such as S3 buckets, use this name. (ex: devx)
# PRIMARY_REGION - AWS region that will serve as primary for the workload
# SECONDARY_REGION - AWS region that will serve as the failover region for the workload
# DOMAIN_NAME - the Route53 private hosted zone domain name that should be created for this workload

ENV="-dev"
PRIMARY_REGION=us-east-1
SECONDARY_REGION=us-west-2
SES_IDENTITY=sender@example.com
EMPTY_LIST='{ "Objects": null }'
.DEFAULT_GOAL := test-creds
MAKE=/usr/bin/make

global:
	@echo "Installing global infrastructure Cloudformation stack..."
	$(eval result:=$(shell aws cloudformation create-stack --stack-name global-base$(ENV) --region $(PRIMARY_REGION) --output text --template-body file://globalResources.yml --capabilities CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND --parameters ParameterKey=PrimaryRegion,ParameterValue=$(PRIMARY_REGION) ParameterKey=SecondaryRegion,ParameterValue=$(SECONDARY_REGION) ParameterKey=Env,ParameterValue=$(ENV)))
	@aws cloudformation wait stack-create-complete --stack-name global-base$(ENV) --region $(PRIMARY_REGION)
	@echo "Finished global infrastructure stack"

primary-vpc:
	@echo "Installing resources into primary region..."
	@echo "Installing VPC infrastructure Cloudformation stack..."
	$(eval result:=$(shell aws cloudformation create-stack --stack-name regionalVPC$(ENV) --capabilities CAPABILITY_IAM --region $(PRIMARY_REGION) --output text --template-body file://regionalVpc.yml --parameters ParameterKey=Env,ParameterValue=$(ENV)))
	@aws cloudformation wait stack-create-complete --stack-name regionalVPC$(ENV) --region $(PRIMARY_REGION)

primary-app:
	@echo "Building and Deploying Application..."
	sam build -t ./samTemplate.yaml
	sam deploy --resolve-s3 --stack-name batch$(ENV) --capabilities CAPABILITY_IAM --region $(PRIMARY_REGION) --no-confirm-changeset --parameter-overrides Env=$(ENV) SESSender=$(SES_IDENTITY) SESRecipient=$(SES_IDENTITY) SESIdentityName=$(SES_IDENTITY) SourceBucket=$(shell aws cloudformation list-stack-resources --region $(PRIMARY_REGION) --stack-name regionalVPC$(ENV) --query "StackResourceSummaries[?LogicalResourceId=='SourceBucket'].{PhysicalResourceId: PhysicalResourceId}" --output text) --disable-rollback

secondary-app:
	@echo "Building and Deploying Application..."
	sam deploy --resolve-s3 --stack-name batch$(ENV) --capabilities CAPABILITY_IAM --region $(SECONDARY_REGION) --no-confirm-changeset --parameter-overrides Env=$(ENV) SESSender=$(SES_IDENTITY) SESRecipient=$(SES_IDENTITY) SESIdentityName=$(SES_IDENTITY) SourceBucket=$(shell aws cloudformation list-stack-resources --region $(SECONDARY_REGION) --stack-name regionalVPC$(ENV) --query "StackResourceSummaries[?LogicalResourceId=='SourceBucket'].{PhysicalResourceId: PhysicalResourceId}" --output text) --disable-rollback

secondary-vpc:
	@echo "Installing resources into secondary region..."
	@echo "Installing VPC infrastructure Cloudformation stack..."
	$(eval result:=$(shell aws cloudformation create-stack --stack-name regionalVPC$(ENV) --capabilities CAPABILITY_IAM --region $(SECONDARY_REGION) --output text --template-body file://regionalVpc.yml --parameters ParameterKey=Env,ParameterValue=$(ENV)))
	@aws cloudformation wait stack-create-complete --stack-name regionalVPC$(ENV) --region $(SECONDARY_REGION)

global-routing:
	@echo "Creating global routing resources..."
	$(eval result:=$(shell aws cloudformation create-stack --stack-name global-routing$(ENV) --region $(PRIMARY_REGION) --output text --template-body file://globalRouting.yml --capabilities CAPABILITY_IAM --parameters ParameterKey=Env,ParameterValue=$(ENV) ParameterKey=PrimaryRegion,ParameterValue=$(PRIMARY_REGION) ParameterKey=SecondaryRegion,ParameterValue=$(SECONDARY_REGION) ParameterKey=PrimaryRegionBucketSecretName,ParameterValue=SourceBucket-$(PRIMARY_REGION)$(ENV) ParameterKey=SecondaryRegionBucketSecretName,ParameterValue=SourceBucket-$(SECONDARY_REGION)$(ENV) ))
	@aws cloudformation wait stack-create-complete --stack-name global-routing$(ENV) --region $(PRIMARY_REGION)

dashboard:
	@echo "Creating dashboard..."
	$(eval result:=$(shell aws cloudformation create-stack --stack-name dashboard$(ENV) --region $(PRIMARY_REGION) --output text --template-body file://dashboard-template.yml --capabilities CAPABILITY_IAM --parameters ParameterKey=Env,ParameterValue=$(ENV) ParameterKey=PrimaryRegion,ParameterValue=$(PRIMARY_REGION) ParameterKey=SecondaryRegion,ParameterValue=$(SECONDARY_REGION) ))
	@aws cloudformation wait stack-create-complete --stack-name dashboard$(ENV) --region $(PRIMARY_REGION)
	@echo "Deploy Complete!"

chaos-primary:
	@echo "Creating Chaos Testing resources in Primary Region..."
	$(eval result:=$(shell aws cloudformation create-stack --stack-name chaos$(ENV) --region $(PRIMARY_REGION) --output text --template-body file://fisTemplate.yml --capabilities CAPABILITY_IAM))
	@aws cloudformation wait stack-create-complete --stack-name chaos$(ENV) --region $(PRIMARY_REGION)
	@echo "Deploy Complete in Primary Region!"

chaos-secondary:
	@echo "Creating Chaos Testing resources in Secondary Region..."
	$(eval result:=$(shell aws cloudformation create-stack --stack-name chaos$(ENV) --region $(SECONDARY_REGION) --output text --template-body file://fisTemplate.yml --capabilities CAPABILITY_IAM))
	@aws cloudformation wait stack-create-complete --stack-name chaos$(ENV) --region $(SECONDARY_REGION)
	@echo "Deploy Complete in Secondary Region!"

deploy: test-creds global primary-vpc secondary-vpc global-routing primary-app secondary-app dashboard

chaos: test-creds chaos-primary chaos-secondary

destroy-chaos:
	@echo "Removing Chaos Resources..."
	@aws cloudformation delete-stack --stack-name chaos$(ENV) --region $(PRIMARY_REGION)
	@aws cloudformation wait stack-delete-complete --stack-name chaos$(ENV) --region $(PRIMARY_REGION)
	@echo "Destroyed Chaos Resources in Primary Region!"

	@aws cloudformation delete-stack --stack-name chaos$(ENV) --region $(SECONDARY_REGION)
	@aws cloudformation wait stack-delete-complete --stack-name chaos$(ENV) --region $(SECONDARY_REGION)
	@echo "Destroyed Chaos Resources in Secondary Region!"

destroy-all:
	@echo "Removing all cloudformation stacks!!"
	@aws cloudformation delete-stack --stack-name dashboard$(ENV) --region $(PRIMARY_REGION)
	@aws cloudformation wait stack-delete-complete --stack-name dashboard$(ENV) --region $(PRIMARY_REGION)

	@echo "Removing application from secondary region"
	@-sam delete --stack-name batch$(ENV) --region $(SECONDARY_REGION) --no-prompts

	@echo "Removing application from primary region"
	@-sam delete --stack-name batch$(ENV) --region $(PRIMARY_REGION) --no-prompts

	@echo "Removing global routing resources"
	@aws cloudformation delete-stack --stack-name global-routing$(ENV) --region $(PRIMARY_REGION)
	@aws cloudformation wait stack-delete-complete --stack-name global-routing$(ENV) --region $(PRIMARY_REGION)

	@echo "Cleaning up S3 Buckets..."
	$(eval result:=$(shell aws cloudformation list-stack-resources --region $(SECONDARY_REGION) --stack-name regionalVPC$(ENV) --query "StackResourceSummaries[?LogicalResourceId=='LoggingBucket'].{PhysicalResourceId: PhysicalResourceId}" --output text |cut -d: -f6 ))
	./cleanup.sh $(result)

	$(eval result:=$(shell aws cloudformation list-stack-resources --region $(SECONDARY_REGION) --stack-name regionalVPC$(ENV) --query "StackResourceSummaries[?LogicalResourceId=='SourceBucket'].{PhysicalResourceId: PhysicalResourceId}" --output text |cut -d: -f6 ))
	./cleanup.sh $(result)

	$(eval result:=$(shell aws cloudformation list-stack-resources --region $(PRIMARY_REGION) --stack-name regionalVPC$(ENV) --query "StackResourceSummaries[?LogicalResourceId=='LoggingBucket'].{PhysicalResourceId: PhysicalResourceId}" --output text |cut -d: -f6 ))
	./cleanup.sh $(result)

	$(eval result:=$(shell aws cloudformation list-stack-resources --region $(PRIMARY_REGION) --stack-name regionalVPC$(ENV) --query "StackResourceSummaries[?LogicalResourceId=='SourceBucket'].{PhysicalResourceId: PhysicalResourceId}" --output text |cut -d: -f6 ))
	./cleanup.sh $(result)
	@echo "S3 Buckets emptied..."

	@echo "Remove primary regional stacks..."
	@aws cloudformation delete-stack --stack-name regionalVPC$(ENV) --region $(PRIMARY_REGION)
	@aws cloudformation wait stack-delete-complete --stack-name regionalVPC$(ENV) --region $(PRIMARY_REGION)
	
	@echo "Remove secondary regional stacks..."
	@aws cloudformation delete-stack --stack-name regionalVPC$(ENV) --region $(SECONDARY_REGION)
	@aws cloudformation wait stack-delete-complete --stack-name regionalVPC$(ENV) --region $(SECONDARY_REGION)

	@echo "Remove global stack..."
	@aws cloudformation delete-stack --stack-name global-base$(ENV) --region $(PRIMARY_REGION)
	@aws cloudformation wait stack-delete-complete --stack-name global-base$(ENV) --region $(PRIMARY_REGION)

clean:
	@echo "To remove all stacks deployed by this solution, run 'make destroy-all'"

test-creds:
	@echo "Current AWS session:"
	@aws sts get-caller-identity