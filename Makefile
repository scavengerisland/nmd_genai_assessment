.PHONY: install check format test test-cov clean docker-build docker-push deploy update-lambdas tf-init tf-plan tf-apply tf-destroy upload-data

# --- Development ---
install:
	uv sync

check:
	uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/

format:
	uv run ruff check --fix src/ tests/ && uv run ruff format src/ tests/

test:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ --cov=src --cov-report=term-missing

clean:
	rm -rf .pytest_cache __pycache__ src/**/__pycache__

# --- Docker ---
docker-build:
	docker build --platform linux/arm64 --provenance=false --no-cache -t nmd_genai_assessment .

docker-push:
	@ECR_REPO=$$(cd terraform/live/candidate && terraform output -raw ecr_repository_url) && \
	AWS_ACCOUNT=$$(aws sts get-caller-identity --query Account --output text) && \
	aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin "$$AWS_ACCOUNT.dkr.ecr.us-west-2.amazonaws.com" && \
	docker tag nmd_genai_assessment "$$ECR_REPO:latest" && \
	docker push "$$ECR_REPO:latest" && \
	echo "Pushed to $$ECR_REPO:latest"

deploy: docker-build docker-push
	@echo "Image pushed. Run 'make update-lambdas' to update the Lambda functions."

update-lambdas:
	@set -e; \
	ECR_REPO=$$(cd terraform/live/candidate && terraform output -raw ecr_repository_url); \
	for fn in preprocess classify extract aggregate; do \
		FUNC_NAME=$$(cd terraform/live/candidate && terraform output -raw $${fn}_lambda_name); \
		if [ -z "$$FUNC_NAME" ]; then echo "ERROR: no Terraform output $${fn}_lambda_name" >&2; exit 1; fi; \
		echo "Updating $$FUNC_NAME..."; \
		aws lambda update-function-code --function-name "$$FUNC_NAME" --image-uri "$$ECR_REPO:latest" > /dev/null; \
		aws lambda wait function-updated --function-name "$$FUNC_NAME"; \
	done; \
	echo "Lambda functions updated."

# --- Terraform ---
tf-init:
	cd terraform/live/candidate && terraform init

tf-plan:
	cd terraform/live/candidate && terraform plan -var-file=terraform.tfvars

tf-apply:
	cd terraform/live/candidate && terraform apply -var-file=terraform.tfvars

tf-destroy:
	cd terraform/live/candidate && terraform destroy -var-file=terraform.tfvars

# --- Data ---
upload-data:
	@for f in data/*.json; do \
		echo "Uploading $$f to s3://$${S3_BUCKET_NAME}/uploads/$$(basename $$f)"; \
		aws s3 cp "$$f" "s3://$${S3_BUCKET_NAME}/uploads/$$(basename $$f)"; \
	done
