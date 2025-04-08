import json
import boto3
import os
from lip_sync import generate_lip_sync_data
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# AWS clients
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
polly = boto3.client('polly', region_name='us-east-1')
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
appsync = boto3.client('appsync')

# Configuration from environment variables
BUCKET_NAME = 'visual-chatbot-audio'
TABLE_NAME = 'ChatHistory'
APPSYNC_API_ID_RAW = os.environ["APPSYNC_API_ID"]

# Extract API ID from ARN if necessary
if "arn:aws:appsync" in APPSYNC_API_ID_RAW:
    APPSYNC_API_ID = APPSYNC_API_ID_RAW.split('/')[-1]  # Extract the ID from ARN
else:
    APPSYNC_API_ID = APPSYNC_API_ID_RAW
logger.info(f"Using AppSync API ID: {APPSYNC_API_ID}")

def lambda_handler(event, context):
    """
    Lambda handler for processing chat requests.
    - Receives user input via API Gateway.
    - Generates a response using Bedrock (Claude).
    - Converts response to speech with Polly.
    - Analyzes lip sync with waveform analysis.
    - Stores audio in S3 and logs in DynamoDB.
    - Pushes real-time update to AppSync.
    """
    try:
        # Parse user input from API Gateway event
        body = json.loads(event['body'])
        user_input = body.get('message')
        if not user_input:
            raise ValueError("No message provided in request body")
        logger.info(f"Received user input: {user_input}")

        # Step 1: Generate response with Bedrock (Anthropic Claude)
        response = bedrock.invoke_model(
            modelId='anthropic.claude-v2',
            body=json.dumps({
                'prompt': f'Human: {user_input} Assistant: ',
                'max_tokens_to_sample': 300,
                'temperature': 0.7
            }),
            contentType='application/json'
        )
        response_text = json.loads(response['body'].read())['completion'].strip()
        logger.info(f"Generated response: {response_text}")

        # Step 2: Convert response to speech with Polly
        polly_response = polly.synthesize_speech(
            Text=response_text,
            OutputFormat='mp3',
            VoiceId='Joanna'  # High-quality voice
        )
        audio_path = '/tmp/response.mp3'
        with open(audio_path, 'wb') as f:
            f.write(polly_response['AudioStream'].read())
        logger.info("Converted text to speech")

        # Step 3: Generate lip sync data
        lip_sync_data = generate_lip_sync_data(audio_path)
        logger.info(f"Generated lip sync data with {len(lip_sync_data)} frames")

        # Step 4: Upload audio to S3
        audio_key = f'response_{context.aws_request_id}.mp3'
        s3.upload_file(audio_path, BUCKET_NAME, audio_key, ExtraArgs={'ContentType': 'audio/mpeg'})
        audio_url = f'https://{BUCKET_NAME}.s3.amazonaws.com/{audio_key}'
        logger.info(f"Uploaded audio to S3: {audio_url}")

        # Step 5: Store conversation in DynamoDB
        table = dynamodb.Table(TABLE_NAME)
        table.put_item(Item={
            'request_id': context.aws_request_id,
            'user_input': user_input,
            'response': response_text,
            'audio_key': audio_key,
            'timestamp': int(time.time())
        })
        logger.info("Stored conversation in DynamoDB")

        # Step 6: Push real-time update to AppSync
        appsync_response = appsync.graphql(
            apiId=APPSYNC_API_ID,
            query='''
                mutation PublishResponse($response: String!, $audioUrl: String!, $lipSync: AWSJSON!) {
                    publishResponse(response: $response, audioUrl: $audioUrl, lipSync: $lipSync) {
                        response
                        audioUrl
                        lipSync
                    }
                }
            ''',
            variables={
                'response': response_text,
                'audioUrl': audio_url,
                'lipSync': json.dumps(lip_sync_data)
            }
        )
        logger.info(f"Pushed response to AppSync: {appsync_response}")

        # Clean up temporary file
        os.remove(audio_path)

        # Return success response to API Gateway
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Processing complete'})
        }

    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

if __name__ == "__main__":
    # For local testing (mock event and context)
    os.environ["APPSYNC_API_ID"] = "test-api-id"  # Set manually for local testing
    mock_event = {
        'body': json.dumps({'message': 'Hello, how are you?'})
    }
    mock_context = type('MockContext', (), {'aws_request_id': 'test-id'})()
    print(lambda_handler(mock_event, mock_context))
