import json
import boto3
import os
from lip_sync import generate_lip_sync_data

# AWS clients
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
polly = boto3.client('polly', region_name='us-east-1')
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
appsync = boto3.client('appsync')

# Config
BUCKET_NAME = 'visual-chatbot-audio'
TABLE_NAME = 'ChatHistory'
APPSYNC_API_ID = '<YOUR_APPSYNC_API_ID>'  # Replace after deployment

def lambda_handler(event, context):
    body = json.loads(event['body'])
    user_input = body.get('message')

    # Call Bedrock (Claude)
    response = bedrock.invoke_model(
        modelId='anthropic.claude-v2',
        body=json.dumps({
            'prompt': f'Human: {user_input} Assistant: ',
            'max_tokens_to_sample': 300
        }),
        contentType='application/json'
    )
    response_text = json.loads(response['body'].read())['completion'].strip()

    # Convert to speech with Polly
    polly_response = polly.synthesize_speech(
        Text=response_text,
        OutputFormat='mp3',
        VoiceId='Joanna'  # High-quality voice
    )
    audio_path = '/tmp/response.mp3'
    with open(audio_path, 'wb') as f:
        f.write(polly_response['AudioStream'].read())

    # Generate lip sync data
    lip_sync_data = generate_lip_sync_data(audio_path)

    # Upload audio to S3
    audio_key = f'response_{context.aws_request_id}.mp3'
    s3.upload_file(audio_path, BUCKET_NAME, audio_key, ExtraArgs={'ContentType': 'audio/mpeg'})

    # Store in DynamoDB
    table = dynamodb.Table(TABLE_NAME)
    table.put_item(Item={
        'request_id': context.aws_request_id,
        'user_input': user_input,
        'response': response_text,
        'audio_key': audio_key,
        'timestamp': int(os.time())
    })

    # Push real-time update via AppSync
    appsync.start_graphql_mutation(
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
            'audioUrl': f'https://{BUCKET_NAME}.s3.amazonaws.com/{audio_key}',
            'lipSync': json.dumps(lip_sync_data)
        }
    )

    # Clean up
    os.remove(audio_path)

    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Processing complete'})
    }
