import datetime
import pytz
import json
import string
import decimal
import random
import types


###########################################################################
# random string methods (for generating test data)
###########################################################################

def random_alpha_string(length, contains_spaces=False):
    if contains_spaces:
        chars = string.ascii_uppercase + ' '
    else:
        chars = string.ascii_uppercase
    return ''.join(random.SystemRandom().choice(chars) for _ in range(length))

def random_numeric_string(length):
    chars = string.digits
    return ''.join(random.SystemRandom().choice(chars) for _ in range(length))

def random_an_string(length, contains_spaces=False):
    if contains_spaces:
        chars = string.ascii_uppercase + string.digits + ' '
    else:
        chars = string.ascii_uppercase + string.digits
    return ''.join(random.SystemRandom().choice(chars) for _ in range(length))

def random_date_days(old_day_range, new_day_range):
    now = datetime.datetime.today()
    days = random.randint(old_day_range, new_day_range)
    return now + datetime.timedelta(days = days)

def random_date_dates(old_date, new_date):
    now = datetime.datetime.today()
    return random_date_days((today - old_date).days, (today - new_date).days)


###########################################################################
# random object methods (for generating test data)
###########################################################################

def gen_user():
    user = {
        "updatedAt":random_date_days(-5, -1),
        "createdAt":random_date_days(-20, -5),
        "username":random_alpha_string(20),
        "email":random_alpha_string(20) + '@' + random_alpha_string(12) + '.' + random_alpha_string(3),
        "emailVerified":True,
        "lastName":random_alpha_string(20),
        "hasLoggedIn":True,
        "permission":random_alpha_string(20),
        "isActive":True,
        "publicEmail":random_alpha_string(20) + '@' + random_alpha_string(12) + '.' + random_alpha_string(3),
        "firstName":random_alpha_string(8),
    }
    return user

def gen_team(user):
    team = {
        "updatedAt":random_date_days(-5, -1),
        "createdAt":random_date_days(-20, -5),
        "color":random_alpha_string(8),
        "name":random_alpha_string(20),
        "isActive":True,
    }
    return team

def gen_inspection(user, team):
    inspection = {
        "teamID":team['_id'],
        "updatedAt":random_date_days(-5, -1),
        "createdAt":random_date_days(-20, -5),
        "start":random_date_days(-20, -5),
        "number":random_numeric_string(8),
        "subtext":random_alpha_string(40, contains_spaces=True),
        "end":random_date_days(-5, -1),
        "userId":user['_id'],
        "subtitle":random_alpha_string(40, contains_spaces=True),
        "title":random_alpha_string(40, contains_spaces=True),
        "uploaded":True,
        "project":random_alpha_string(40, contains_spaces=True),
        "isSubmitted":True,
        "isActive":True,
    }
    return inspection

def gen_observation(inspection):
    observation = {
        "inspectionId":inspection['_id'],
        "pinnedAt":random_date_days(-5, -1),
        "updatedAt":random_date_days(-5, -1),
        "createdAt":random_date_days(-20, -5),
        "title":random_alpha_string(40, contains_spaces=True),
        "requirement":random_alpha_string(40, contains_spaces=True),
        "observationDescription":random_alpha_string(40, contains_spaces=True),
    }
    return observation

def gen_audio(observation):
    audio = {
        "updatedAt":random_date_days(-5, -1),
        "createdAt":random_date_days(-20, -5),
        "notes":random_alpha_string(40, contains_spaces=True),
        "index":random.randint(1, 100),
        "title":random_alpha_string(40, contains_spaces=True),
        "inspectionId":observation['inspectionId'],
        "observationId":observation['_id'],
    }
    return audio

def gen_photo(observation):
    photo = {
        "observationId":observation['_id'],
        "updatedAt":random_date_days(-5, -1),
        "createdAt":random_date_days(-20, -5),
        "caption":random_alpha_string(40, contains_spaces=True),
        "timestamp":random_date_days(-5, -1),
        "index":random.randint(1, 100),
    }
    return photo

def gen_video(observation):
    video = {
        "updatedAt":random_date_days(-5, -1),
        "createdAt":random_date_days(-20, -5),
        "observationId":observation['_id'],
        "inspectionId":observation['inspectionId'],
        "index":random.randint(1, 100),
        "notes":random_alpha_string(40, contains_spaces=True),
        "title":random_alpha_string(40, contains_spaces=True),
    }
    return video
