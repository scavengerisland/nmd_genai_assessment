output "s3_bucket_name" {
  description = "S3 bucket for document uploads"
  value       = module.s3.bucket_name
}

output "ecr_repository_url" {
  description = "ECR repository URL for Lambda Docker images"
  value       = module.ecr.repository_url
}

output "state_machine_arn" {
  description = "Step Functions state machine ARN"
  value       = module.step_functions.state_machine_arn
}

output "eventbridge_rule_name" {
  description = "EventBridge rule name"
  value       = module.eventbridge.rule_name
}

# Read by `make update-lambdas`.
output "preprocess_lambda_name" {
  description = "Preprocess Lambda function name"
  value       = module.lambda.preprocess_name
}

output "classify_lambda_name" {
  description = "Classify Lambda function name"
  value       = module.lambda.classify_name
}

output "extract_lambda_name" {
  description = "Extract Lambda function name"
  value       = module.lambda.extract_name
}

output "aggregate_lambda_name" {
  description = "Aggregate Lambda function name"
  value       = module.lambda.aggregate_name
}
