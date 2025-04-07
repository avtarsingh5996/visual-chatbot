#!/bin/bash

# Variables
LAMBDA_NAME="VisualChatBotLambda"
ROLE_NAME="LambdaBedrockRole"
BUCKET_NAME="visual-chatbot-audio"
REGION="us-east-1"

# Create S3 buckets
aws s3 mb s3://$BUCKET_NAME --region $REGION
aws s3 mb s3://visual-chatbot-frontend --region $REGION

# Create IAM role
aws iam create-role --role-name $ROLE_NAME --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam put-role-policy --role-name $ROLE_NAME --policy-name BedrockS3Access --policy-document file://../infra/lambda_role.json

# Package Lambda
pip install -r requirements.txt -t .
zip -r lambda.zip . -x "*.git*"

# Deploy Lambda
aws lambda create-function \
    --function-name $LAMBDA_NAME \
    --zip-file fileb://lambda.zip \
    --handler lambda_function.lambda_handler \
    --runtime python3.9 \
    --role $(aws iam get-role --role-name $ROLE_NAME --query Role.Arn --output text) \
    --timeout 30 \
    --memory-size 1024

# Create API Gateway
API_ID=$(aws apigateway create-rest-api --name "VisualChatBotAPI" --query 'id' --output text)
ROOT_ID=$(aws apigateway get-resources --rest-api-id $API_ID --query 'items[0].id' --output text)
aws apigateway put-method --rest-api-id $API_ID --resource-id $ROOT_ID --http-method POST --authorization-type NONE
aws apigateway put-integration \
    --rest-api-id $API_ID \
    --resource-id $ROOT_ID \
    --http-method POST \
    --type AWS_PROXY \
    --integration-http-method POST \
    --uri arn:aws:apigateway:$REGION:lambda:path/2015-03-31/functions/$(aws lambda get-function --function-name $LAMBDA_NAME --query 'Configuration.FunctionArn' --output text)/invocations
aws apigateway create-deployment --rest-api-id $API_ID --stage-name prod

# Output API URL
echo "API URL: https://$API_ID.execute-api.$REGION.amazonaws.com/prod"

# Upload frontend to S3
aws s3 sync ../frontend/ s3://visual-chatbot-frontend --acl public-read
echo "Frontend URL: http://visual-chatbot-frontend.s3-website-$REGION.amazonaws.com"
