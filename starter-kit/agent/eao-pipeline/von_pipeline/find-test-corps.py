#!/usr/bin/python
import psycopg2
from pymongo import MongoClient
import datetime
from von_pipeline.config import config
from tests.gen_test_data import *


print("TODO load some test data")
mdb_config = config(section='eao_data')
print(mdb_config['host'], mdb_config['port'], mdb_config['database'])
client = MongoClient('mongodb://%s:%s@%s:%s' % (mdb_config['user'], mdb_config['password'], mdb_config['host'], mdb_config['port']))
db = client[mdb_config['database']]

users = db['users']
teams = db['teams']
inspections = db['inspections']
observations = db['observations']
audios = db['audios']
photos = db['photos']
videos = db['videos']

user = gen_user()
user_id = users.insert_one(user).inserted_id
user = users.find_one({"_id": user_id})

team = gen_team(user)
team_id = teams.insert_one(team).inserted_id
team = teams.find_one({"_id": team_id})

inspection = gen_inspection(user, team)
inspection_id = inspections.insert_one(inspection).inserted_id
inspection = inspections.find_one({"_id": inspection_id})

observation = gen_observation(inspection)
observation_id = observations.insert_one(observation).inserted_id
observation = observations.find_one({"_id": observation_id})

audio = gen_audio(observation)
audio_id = audios.insert_one(audio).inserted_id

photo = gen_photo(observation)
photo_id = photos.insert_one(photo).inserted_id

video = gen_video(observation)
video_id = videos.insert_one(video).inserted_id

collections = db.collection_names(include_system_collections=False)
print(collections)
