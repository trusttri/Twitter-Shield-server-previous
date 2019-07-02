#Author : Sonali Tandon (sonalitandon24@gmail.com)


from flask import Flask, render_template, request,jsonify
import json,requests,twitter,re,config,os
#import fastText
from flask_cors import CORS, cross_origin
from langdetect import detect
from googleapiclient import discovery
from flask import Response
import tweepy
from googleapiclient import discovery

app = Flask(__name__)
CORS(app, support_credentials=True)


app.config["DEBUG"] = True
BUCKET_NAME = 'pretrained-models'
MODEL_FILE_NAME = 'model_politics.bin'
MODEL_LOCAL_PATH = MODEL_FILE_NAME

consumer_key = "ULVFOWWRwPBG31JmCSk3pA9WY"
consumer_secret = "GkpPuajWIi8OwFNHJMnKaAvLBCQcQZdiNnEViM44eqvTvAXkf7"
access_key = "973403711518183425-CNAn0AQYiT074O0XyALXdU2LiJUzGSg"
access_secret = "s986l8COxFydEgyOCSuHrtGRSldyunsKfZh59TRyx1tVd"
auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
auth.set_access_token(access_key, access_secret)
api = tweepy.API(auth)

# api = twitter.Api(consumer_key='ULVFOWWRwPBG31JmCSk3pA9WY',
#                       consumer_secret='GkpPuajWIi8OwFNHJMnKaAvLBCQcQZdiNnEViM44eqvTvAXkf7',
#                       access_token_key='973403711518183425-CNAn0AQYiT074O0XyALXdU2LiJUzGSg',
#                       access_token_secret='s986l8COxFydEgyOCSuHrtGRSldyunsKfZh59TRyx1tVd',
#                       tweet_mode='extended'
#                   )


API_KEY='AIzaSyDlpWkkECadgt55aVD0tKIrTcjHpIBk3i8'



'''
1. Checks if tweets are in English 2. Removes links, @ 3. Checks if tweet
'''
def clean_tweets(tweets):
	# cleaned_tweets = []
	cleaned_tweets = {}
	for tweet in tweets:
		#print('before clean ' + tweet)
		try:
			if(detect(tweet) == 'en'):
				cleaned_tweet = re.sub(r'(@\S+)|(http\S+)', " ", str(tweet))
				if(cleaned_tweet and cleaned_tweet.strip()):
					# print('\n')
					# print('After clean ' + tweet)
					# print('\n')
					# cleaned_tweets.append(tweet)
					cleaned_tweets[tweet] = cleaned_tweet
		except Exception as e:
			print('Exception wheen cleaning- Tweet in response: ' + tweet)
			print(e)
	print(len(cleaned_tweets))
	return cleaned_tweets
			
def get_user(screenName):
	user = api.GetUser(None,screenName,True,True)
	return user

def get_user_timeline(screenName,tweetCount):
	statuses = api.user_timeline(screen_name = screenName,count=tweetCount, tweet_mode="extended")

	status_texts = []
	for tweet in statuses:
		if hasattr(tweet, 'retweeted_status'):
			status_texts.append(tweet.retweeted_status.full_text)
		else:
			status_texts.append(tweet.full_text)

	#print(status_texts)
	return status_texts


'''
routes 
'''
@app.route('/')
def index():
	return 'Hello from Twitter-Shield Server'


''' 
Current version: using perspective API 
'''
@app.route('/toxicityscore', methods =['GET'])
def toxicity_score():
	screen_name = request.args.get('user')

	threshold = request.args.get('threshold')
	user_perspective_scores = {}

	#models user choses + score - probably store this in db too! 
	#set default as zero in front end 

	models_setting_json = {}
	for model in config.PERSPECTIVE_MODELS:
		if(request.args.get(model.lower())):
			models_setting_json[model] = {'scoreThreshold': request.args.get(model.lower())}
		else:
			models_setting_json[model] = {'scoreThreshold': '0'}

	#print(models_setting_json)

	tweet_count = 200
	#get tweets on user's timeline
	user_timeline_tweets = get_user_timeline(screen_name, tweet_count)
	cleaned_user_timeline_tweets = clean_tweets(user_timeline_tweets)	


	tweets_with_perspective_scores = get_tweet_perspective_scores(cleaned_user_timeline_tweets, models_setting_json)
	# insert into db
	user_perspective_scores = get_user_perspective_score(tweets_with_perspective_scores)
	# insert into db
	user_perspective_scores['username'] = screen_name
	user_perspective_scores['tweets_considered_count'] = len(tweets_with_perspective_scores)
	user_perspective_scores['tweets_with_scores'] = tweets_with_perspective_scores
	score = str(user_perspective_scores['TOXICITY']['score'])
	print('threshold' + threshold)
	print('score: ' + score)

	if (float(score) >= float(threshold)):
		print("ABOVE")
		user_perspective_scores['visualize'] = score
	else:
		print("BELOW")
		user_perspective_scores['visualize'] = 'Below threshold'
	#
	# return Response(response_text,mimetype='plain/text')
	#return jsonify({'key':'jk'})

	# print(user_perspective_scores)
	# print('-----below should return dictionary')
	# print(type(user_perspective_scores)) # this should return dictionary...
	return jsonify(user_perspective_scores)


def get_user_perspective_score(tweets_with_perspective_scores):
	user_perspective_scores_json = {}


	for model in config.PERSPECTIVE_MODELS:
		temp_json = {}
		temp_json['total'] = 0
		temp_json['count'] = 0 
		temp_json['score'] = 0

		for obj in tweets_with_perspective_scores:
			if model in obj['tweet_scores']:
				temp_json['total'] += obj['tweet_scores'][model]
				temp_json['count'] += 1
		if(temp_json['count']!=0):
			temp_json['score'] = temp_json['total']/temp_json['count']
		user_perspective_scores_json[model] = temp_json

	#print(user_perspective_scores_json)
	return user_perspective_scores_json


def get_tweet_perspective_scores(tweets, models_setting_json):
	service = discovery.build('commentanalyzer', 'v1alpha1', developerKey=API_KEY)
	tweets_with_perspective_scores = []
	tweet_count = 0
	
	for original_tweet, cleaned_tweet in tweets.items():
		model_response_json ={}
		analyze_request = {
				  'comment': { 'text': cleaned_tweet},
				  'requestedAttributes': models_setting_json}
		try:
			response = service.comments().analyze(body=analyze_request).execute()
			if(response['attributeScores']):
				for model in config.PERSPECTIVE_MODELS:
					if model in response['attributeScores']:
						model_response_json[model] = response['attributeScores'][model]['summaryScore']['value']
				temp_json = {'tweet_scores':model_response_json, 'cleaned_tweet_text':cleaned_tweet, 'original_tweet_text':original_tweet}
				tweets_with_perspective_scores.append(temp_json)
		except Exception as e:
			print('Exception when getting perspective scores - Tweet in response: ' +  original_tweet)
			print(e)
		
	
	# print(json.dumps(tweets_with_perspective_scores,indent=2)) 
	# print('\n')

	return tweets_with_perspective_scores


''' 
functions when using Eshwar models. Not used in current version (using Perspecitve API)
'''

# def make_predictions(tweets):
	# # conn = S3Connection()
	# # bucket = conn.create_bucket(BUCKET_NAME)
	# # key_obj = Key(bucket)
	# # key_obj.key = MODEL_FILE_NAME
	# # contents = key_obj.get_contents_to_filename(MODEL_LOCAL_PATH)


	# predicted_json = [{'tweet':tweet} for tweet in tweets]
	# for model in config.REDDIT_MODELS:
	# 	#r = requests.get('https://s3.us-east-2.amazonaws.com/pretrained-models/model_AskReddit.bin')
	# 	#create_model = fastText.load_model(contents)
	# 	create_model =   fastText.load_model(config.PATH+ 'model_'+model+ config.EXTENSION)

	# 	#create_model = fastText.load_model(r)
	# 	predict_model = create_model.predict(tweets)[0]
	# 	for index,item in enumerate(predicted_json):
	# 		item[model] = int(predict_model[index][0] =='__label__removed')
	# 		if(item[model]):
	# 			if 'models_that_agree' in item:
	# 				item['models_that_agree'].append(model)
	# 			else:
	# 				item['models_that_agree'] = [model]
	# return predicted_json

# def calculate_consensus_score(tweet_json):
# 	user_consensus_count = 0
# 	for item in tweet_json:
# 		user_consensus_count+=item['tweet_score']

# 	#user score = mean of tweet scores 
# 	user_consensus_score = user_consensus_count/len(tweet_json)
# 	return user_consensus_score


# def calculate_tweet_scores(predicted_tweet_json):
# 	for item in predicted_tweet_json:
# 		if 'models_that_agree' in item:
# 			item['tweet_score'] = len(item['models_that_agree'])/len(config.MODELS)
# 		else:
# 			item['tweet_score'] = 0
# 	return predicted_tweet_json


# def get_flagged_tweets(tweet_json):

# 	flagged_tweets = []
# 	for item in tweet_json:
# 		if(item['tweet_score']*100 >= config.MIN_CAP):
# 			flagged_tweets.append(item['tweet'])

# 	return flagged_tweets


# @app.route('/abusivescoremodels', methods = ['GET'])
# def get_score():
# 	master_json = {}
# 	screen_name = request.args.get('user')
# 	#screen_name = 'sonalitandon24'

# 	#set default tweet count = 200 (maximum)
# 	tweet_count = 200

# 	#get tweets on user's timeline
# 	response_user_timeline = get_user_timeline(screen_name,tweet_count)	
# 	#print(response_user_timeline)
# 	user_timeline_tweets = [tweet.text for tweet in response_user_timeline]

# 	#clean user tweets 
# 	cleaned_user_timeline_tweets = clean_tweets(user_timeline_tweets)
# 	#print(cleaned_user_timeline_tweets)

# 	#make predictions (label removed or not)
# 	predicted_tweets_json = make_predictions(cleaned_user_timeline_tweets)
# 	predicted_tweets_json = calculate_tweet_scores(predicted_tweets_json)
# 	master_json['predicted_tweets'] = predicted_tweets_json

# 	#get flagged tweets 
# 	flagged_tweets = get_flagged_tweets(predicted_tweets_json)
# 	master_json['flagged_tweets'] = flagged_tweets

# 	#calculate consensus score 
# 	consensus_score = calculate_consensus_score(master_json['predicted_tweets'])
# 	master_json['screen_name'] = screen_name
# 	master_json['user_consensus_score'] = consensus_score
# 	master_json['number_of_tweets_considered'] = len(master_json['predicted_tweets'])
# 	return jsonify(master_json)

# @app.route('/predict', methods = ['POST', 'GET'])
# def predict_tweets():
# 	master_json = {}
# 	tweets = json.loads(request.args.get('tweets'))
# 	cleaned_tweets = clean_tweets(tweets)
# 	predicted_tweets_json = make_predictions(cleaned_tweets)
# 	predicted_tweets_json = calculate_tweet_scores(predicted_tweets_json)
# 	master_json['predicted_tweets'] = predicted_tweets_json
# 	flagged_tweets = get_flagged_tweets(predicted_tweets_json)
# 	master_json['flagged_tweets'] = flagged_tweets
	# return jsonify(master_json)


'''
Added in order to prevent CORS issue
'''
@app.after_request
def add_headers(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    return response

if __name__ == '__main__':
    app.run()
