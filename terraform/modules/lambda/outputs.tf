output "preprocess_arn" { value = aws_lambda_function.preprocess.arn }
output "classify_arn" { value = aws_lambda_function.classify.arn }
output "extract_arn" { value = aws_lambda_function.extract.arn }
output "aggregate_arn" { value = aws_lambda_function.aggregate.arn }

output "preprocess_name" { value = aws_lambda_function.preprocess.function_name }
output "classify_name" { value = aws_lambda_function.classify.function_name }
output "extract_name" { value = aws_lambda_function.extract.function_name }
output "aggregate_name" { value = aws_lambda_function.aggregate.function_name }
