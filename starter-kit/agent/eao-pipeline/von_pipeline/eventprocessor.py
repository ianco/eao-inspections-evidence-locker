#!/usr/bin/python
 
import psycopg2
from pymongo import MongoClient
from bson.objectid import ObjectId
import datetime
import pytz
import json
import time
import decimal
import random
import hashlib
import types
import traceback
from von_pipeline.config import config


system_type = 'EAO_EL'

site_credential = 'SITE'
site_schema = 'inspection-site.eao-evidence-locker'
site_version = '1.0.0'

inspc_credential = 'INSPC'
inspc_schema = 'safety-inspection.eao-evidence-locker'
inspc_version = '1.0.0'

obsvn_credential = 'OBSVN'
obsvn_schema = 'inspection-document.eao-evidence-locker'
obsvn_version = '1.0.0'

MDB_COLLECTIONS = ['inspections','observations','audios','photos','videos']

CORP_BATCH_SIZE = 3000

MIN_START_DATE = datetime.datetime(datetime.MINYEAR+1, 1, 1)
MAX_END_DATE   = datetime.datetime(datetime.MAXYEAR-1, 12, 31)
DATA_CONVERSION_DATE = datetime.datetime(2004, 3, 26)

# for now, we are in PST time
timezone = pytz.timezone("America/Los_Angeles")

MIN_START_DATE_TZ = timezone.localize(MIN_START_DATE)
MAX_END_DATE_TZ   = timezone.localize(MAX_END_DATE)
DATA_CONVERSION_DATE_TZ = timezone.localize(DATA_CONVERSION_DATE)


# custom encoder to convert wierd data types to strings
class CustomJsonEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime.datetime):
            try:
                tz_aware = timezone.localize(o)
                return tz_aware.astimezone(pytz.utc).isoformat()
            except (Exception) as error:
                if o.year <= datetime.MINYEAR+1:
                    return MIN_START_DATE_TZ.astimezone(pytz.utc).isoformat()
                elif o.year >= datetime.MAXYEAR-1:
                    return MAX_END_DATE_TZ.astimezone(pytz.utc).isoformat()
                return o.isoformat()
        if isinstance(o, (list, dict, str, int, float, bool, type(None))):
            return JSONEncoder.default(self, o)        
        if isinstance(o, decimal.Decimal):
            return (str(o) for o in [o])
        if isinstance(o, set):
            return list(o)
        if isinstance(o, map):
            return list(o)
        if isinstance(o, types.GeneratorType):
            ret = ""
            for s in next(o):
                ret = ret + str(s)
            return ret
        if isinstance(o, ObjectId):
            return str(o)
        return json.JSONEncoder.default(self, o)

class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime.datetime):
            try:
                tz_aware = timezone.localize(o)
                return tz_aware.astimezone(pytz.utc).isoformat()
            except (Exception) as error:
                if o.year <= datetime.MINYEAR+1:
                    return MIN_START_DATE_TZ.astimezone(pytz.utc).isoformat()
                elif o.year >= datetime.MAXYEAR-1:
                    return MAX_END_DATE_TZ.astimezone(pytz.utc).isoformat()
                return o.isoformat()
        return json.JSONEncoder.default(self, o)


# interface to Event Processor database
class EventProcessor:
    def __init__(self):
        try:
            params = config(section='event_processor')
            self.conn = psycopg2.connect(**params)

            mdb_config = config(section='eao_data')
            self.mdb_client = MongoClient('mongodb://%s:%s@%s:%s' % (mdb_config['user'], mdb_config['password'], mdb_config['host'], mdb_config['port']))
            self.mdb_db = self.mdb_client[mdb_config['database']]
        except (Exception) as error:
            print(error)
            print(traceback.print_exc())
            self.conn = None
            self.mdb_client = None
            self.mdb_db = None
            raise

    def __del__(self):
        if self.conn:
            self.conn.close()
            self.conn = None
        if self.mdb_client:
            self.mdb_client.close()
            self.mdb_client = None
            self.mdb_db = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass
 
    # create our base processing tables
    def create_tables(self):
        """ create tables in the PostgreSQL database"""
        commands = (
            """
            CREATE TABLE IF NOT EXISTS LAST_EVENT (
                RECORD_ID SERIAL PRIMARY KEY,
                SYSTEM_TYPE_CD VARCHAR(255) NOT NULL, 
                OBJECT_ID INTEGER NOT NULL,
                OBJECT_DATE TIMESTAMP NOT NULL,
                UPLOAD_DATE TIMESTAMP NOT NULL,
                ENTRY_DATE TIMESTAMP NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS le_stc ON LAST_EVENT 
            (SYSTEM_TYPE_CD);
            """,
            """
            CREATE TABLE IF NOT EXISTS EVENT_HISTORY_LOG (
                RECORD_ID SERIAL PRIMARY KEY,
                SYSTEM_TYPE_CD VARCHAR(255) NOT NULL, 
                PROJECT_ID VARCHAR(255) NOT NULL,
                PROJECT_NAME VARCHAR(255) NOT NULL,
                COLLECTION_TYPE VARCHAR(255) NOT NULL,
                OBJECT_ID INTEGER NOT NULL,
                OBJECT_DATE TIMESTAMP NOT NULL,
                UPLOAD_DATE TIMESTAMP NOT NULL,
                UPLOAD_HASH TIMESTAMP NOT NULL,
                ENTRY_DATE TIMESTAMP NOT NULL,
                PROCESS_DATE TIMESTAMP,
                PROCESS_SUCCESS CHAR,
                PROCESS_MSG VARCHAR(255)
            )
            """,
            """
            -- Hit for counts and queries
            CREATE INDEX IF NOT EXISTS chl_pd_null ON EVENT_HISTORY_LOG 
            (PROCESS_DATE) WHERE PROCESS_DATE IS NULL;
            """,
            """
            -- Hit for query
            CREATE INDEX IF NOT EXISTS chl_ri_pd_null_asc ON EVENT_HISTORY_LOG 
            (RECORD_ID ASC, PROCESS_DATE) WHERE PROCESS_DATE IS NULL;	
            """,
            """
            ALTER TABLE EVENT_HISTORY_LOG
            SET (autovacuum_vacuum_scale_factor = 0.0);
            """,
            """ 
            ALTER TABLE EVENT_HISTORY_LOG
            SET (autovacuum_vacuum_threshold = 5000);
            """,
            """
            ALTER TABLE EVENT_HISTORY_LOG  
            SET (autovacuum_analyze_scale_factor = 0.0);
            """,
            """ 
            ALTER TABLE EVENT_HISTORY_LOG  
            SET (autovacuum_analyze_threshold = 5000);
            """,
            """ 
            REINDEX TABLE EVENT_HISTORY_LOG;
            """,
            """
            CREATE TABLE IF NOT EXISTS CREDENTIAL_LOG (
                RECORD_ID SERIAL PRIMARY KEY,
                SYSTEM_TYPE_CD VARCHAR(255) NOT NULL, 
                CREDENTIAL_TYPE_CD VARCHAR(255) NOT NULL,
                CREDENTIAL_ID VARCHAR(255) NOT NULL,
                SCHEMA_NAME VARCHAR(255) NOT NULL,
                SCHEMA_VERSION VARCHAR(255) NOT NULL,
                CREDENTIAL_JSON JSON NOT NULL,
                CREDENTIAL_HASH VARCHAR(64) NOT NULL, 
                ENTRY_DATE TIMESTAMP NOT NULL,
                PROCESS_DATE TIMESTAMP,
                PROCESS_SUCCESS CHAR,
                PROCESS_MSG VARCHAR(255)
            )
            """,
            """
            -- Hit duplicate credentials
            CREATE UNIQUE INDEX IF NOT EXISTS cl_hash_index ON CREDENTIAL_LOG 
            (CREDENTIAL_HASH);
            """,
            """
            -- Hit for counts and queries
            CREATE INDEX IF NOT EXISTS cl_pd_null ON CREDENTIAL_LOG 
            (PROCESS_DATE) WHERE PROCESS_DATE IS NULL;
            """,
            """
            -- Hit for query
            CREATE INDEX IF NOT EXISTS cl_ri_pd_null_asc ON CREDENTIAL_LOG 
            (RECORD_ID ASC, PROCESS_DATE) WHERE PROCESS_DATE IS NULL;
            """,
            """
            -- Hit for counts
            CREATE INDEX IF NOT EXISTS cl_ps ON CREDENTIAL_LOG
            (process_success)
            """,
            """
            -- Hit for queries
            CREATE INDEX IF NOT EXISTS cl_ps_pd_desc ON CREDENTIAL_LOG
            (process_success, process_date DESC)
            """,
            """
            ALTER TABLE CREDENTIAL_LOG
            SET (autovacuum_vacuum_scale_factor = 0.0);
            """,
            """ 
            ALTER TABLE CREDENTIAL_LOG
            SET (autovacuum_vacuum_threshold = 5000);
            """,
            """
            ALTER TABLE CREDENTIAL_LOG  
            SET (autovacuum_analyze_scale_factor = 0.0);
            """,
            """ 
            ALTER TABLE CREDENTIAL_LOG  
            SET (autovacuum_analyze_threshold = 5000);
            """,
            """ 
            REINDEX TABLE CREDENTIAL_LOG;
            """
            )
        cur = None
        try:
            cur = self.conn.cursor()
            for command in commands:
                cur.execute(command)
            self.conn.commit()
            cur.close()
            cur = None
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            print(traceback.print_exc())
            raise
        finally:
            if cur is not None:
                cur.close()

    # record the last event processed
    def insert_last_event(self, system_type, event_id, event_date):
        """ insert a new event into the event table """
        sql = """INSERT INTO LAST_EVENT (SYSTEM_TYPE_CD, EVENT_ID, EVENT_DATE, ENTRY_DATE)
                 VALUES(%s, %s, %s, %s) RETURNING RECORD_ID;"""
        cur = None
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (system_type, event_id, event_date, datetime.datetime.now(),))
            _record_id = cur.fetchone()[0]
            self.conn.commit()
            cur.close()
            cur = None
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            print(traceback.print_exc())
            raise
        finally:
            if cur is not None:
                cur.close()

    # get the id of the last event processed (at a specific date)
    def get_last_processed_event(self, event_date, system_type):
        cur = None
        try:
            cur = self.conn.cursor()
            cur.execute("""SELECT max(event_id) FROM LAST_EVENT where EVENT_DATE = %s and SYSTEM_TYPE_CD = %s""", (event_date, system_type,))
            row = cur.fetchone()
            cur.close()
            cur = None
            prev_event = row[0]
            if prev_event is None:
                prev_event = 0
            return prev_event
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            print(traceback.print_exc())
            raise
        finally:
            if cur is not None:
                cur.close()

    # get the last event processed timestamp
    def get_last_processed_event_date(self, system_type):
        cur = None
        try:
            cur = self.conn.cursor()
            cur.execute("""SELECT max(event_date) FROM LAST_EVENT where SYSTEM_TYPE_CD = %s""", (system_type,))
            row = cur.fetchone()
            cur.close()
            cur = None
            prev_event = row[0]
            return prev_event
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            print(traceback.print_exc())
            raise
        finally:
            if cur is not None:
                cur.close()

    # insert a record into the "unprocessed corporations" table
    def insert_corporation(self, system_type, prev_event_id, prev_event_dt, last_event_id, last_event_dt, corp_num):
        """ insert a new corps into the corps table """
        sql = """INSERT INTO EVENT_BY_CORP_FILING (SYSTEM_TYPE_CD, PREV_EVENT_ID, PREV_EVENT_DATE, LAST_EVENT_ID, LAST_EVENT_DATE, CORP_NUM, ENTRY_DATE)
                 VALUES(%s, %s, %s, %s, %s, %s, %s) RETURNING RECORD_ID;"""
        cur = None
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (system_type, prev_event_id, prev_event_dt, last_event_id, last_event_dt, 
                                corp_num, datetime.datetime.now(),))
            _record_id = cur.fetchone()[0]
            self.conn.commit()
            cur.close()
            cur = None
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            print(traceback.print_exc())
            raise
        finally:
            if cur is not None:
                cur.close()

    # insert a list of "unprocessed corporations" into the table
    def insert_corporation_list(self, corporation_list):
        """ insert multiple corps into the corps table  """
        sql = """INSERT INTO EVENT_BY_CORP_FILING (SYSTEM_TYPE_CD, PREV_EVENT_ID, PREV_EVENT_DATE, LAST_EVENT_ID, LAST_EVENT_DATE, CORP_NUM, ENTRY_DATE) 
                 VALUES(%s, %s, %s, %s, %s)"""
        cur = None
        try:
            cur = self.conn.cursor()
            cur.executemany(sql, corporation_list)
            self.conn.commit()
            cur.close()
            cur = None
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            print(traceback.print_exc())
            raise
        finally:
            if cur is not None:
                cur.close()

    # update a group of corps into the "unprocessed corp" queue
    def update_corp_event_queue(self, system_type, corps, max_event_id, max_event_date):
        sql = """INSERT INTO EVENT_BY_CORP_FILING (SYSTEM_TYPE_CD, PREV_EVENT_ID, PREV_EVENT_DATE, LAST_EVENT_ID, LAST_EVENT_DATE, CORP_NUM, ENTRY_DATE)
                 VALUES(%s, %s, %s, %s, %s, %s, %s) RETURNING RECORD_ID;"""
        sql2 = """INSERT INTO LAST_EVENT (SYSTEM_TYPE_CD, EVENT_ID, EVENT_DATE, ENTRY_DATE)
                 VALUES(%s, %s, %s, %s) RETURNING RECORD_ID;"""
        cur = None
        try:
            for i,corp in enumerate(corps): 
                cur = self.conn.cursor()
                cur.execute(sql, (system_type, corp['PREV_EVENT']['event_id'], corp['PREV_EVENT']['event_date'], corp['LAST_EVENT']['event_id'], corp['LAST_EVENT']['event_date'], corp['CORP_NUM'], datetime.datetime.now(),))
                _record_id = cur.fetchone()[0]
                cur.close()
                cur = None
            cur = self.conn.cursor()
            cur.execute(sql2, (system_type, max_event_id, max_event_date, datetime.datetime.now(),))
            self.conn.commit()
            cur = None
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            print(traceback.print_exc())
            raise
        finally:
            if cur is not None:
                cur.close()

    # insert data for one corp into the history table
    def insert_corp_history(self, system_type, prev_event_json, last_event_json, corp_num, corp_state, corp_json):
        """ insert a new corps into the corps table """
        sql = """INSERT INTO CORP_HISTORY_LOG (SYSTEM_TYPE_CD, PREV_EVENT, LAST_EVENT, CORP_NUM, CORP_STATE, CORP_JSON, ENTRY_DATE)
                 VALUES(%s, %s, %s, %s, %s, %s, %s) RETURNING RECORD_ID;"""
        cur = None
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (system_type, prev_event_json, last_event_json, corp_num, corp_state, corp_json, datetime.datetime.now(),))
            _record_id = cur.fetchone()[0]
            self.conn.commit()
            cur.close()
            cur = None
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            print(traceback.print_exc())
            raise
        finally:
            if cur is not None:
                cur.close()

    # insert a generated JSON credential into our log
    def insert_json_credential(self, cur, system_cd, cred_type, cred_id, schema_name, schema_version, credential):
        sql = """INSERT INTO CREDENTIAL_LOG (SYSTEM_TYPE_CD, CREDENTIAL_TYPE_CD, CREDENTIAL_ID, 
                SCHEMA_NAME, SCHEMA_VERSION, CREDENTIAL_JSON, CREDENTIAL_HASH, ENTRY_DATE)
                VALUES(%s, %s, %s, %s, %s, %s, %s, %s) RETURNING RECORD_ID;"""
        # create row(s) for corp creds json info
        cred_json = json.dumps(credential, cls=CustomJsonEncoder, sort_keys=True)
        cred_hash = hashlib.sha256(cred_json.encode('utf-8')).hexdigest()
        try:
            print("Storing credential")
            cur.execute("savepoint save_" + cred_type)
            cur.execute(sql, (system_cd, cred_type, cred_id, schema_name, schema_version, cred_json, cred_hash, datetime.datetime.now(),))
            return 1
        except Exception as e:
            # ignore duplicate hash ("duplicate key value violates unique constraint "cl_hash_index"")
            # re-raise all others
            stre = str(e)
            if "duplicate key value violates unique constraint" in stre and "cl_hash_index" in stre:
                print("Hash exception, skipping duplicate credential for corp:", corp_num, cred_type, cred_id, e)
                cur.execute("rollback to savepoint save_" + cred_type)
                #print(cred_json)
                return 0
            else:
                print(traceback.print_exc())
                raise

    def compare_dates(self, first_date, op, second_date, msg):
        if first_date is None:
            print(msg, "first date is None")
        if second_date is None:
            print(msg, "second date is None")
        if op == "==" or op == '=':
            return first_date == second_date
        elif op == "<=":
            return first_date <= second_date
        elif op == "<":
            return first_date < second_date
        elif op == ">":
            return first_date > second_date
        elif op == ">=":
            return first_date >= second_date
        print(msg, "invalid date op", op)
        return False

    # store credentials for the provided corp
    def store_credentials(self, cur, system_typ_cd, corp_cred):
        cred_count = 0
        cred_count = cred_count + self.insert_json_credential(cur, system_typ_cd, corp_cred['cred_type'], corp_cred['id'], 
                                                        corp_cred['schema'], corp_cred['version'], corp_cred['credential'])
        return cred_count

    def build_credential_dict(self, cred_type, schema, version, cred_id, credential):
        cred = {}
        cred['cred_type'] = cred_type
        cred['schema'] = schema
        cred['version'] = version
        cred['credential'] = credential
        cred['id'] = cred_id
        return cred


    # generate a foundational site credential
    def generate_site_credential(self, site):
        site_cred = {}
        site_cred['project_id'] = site['PROJECT_ID']
        site_cred['project_name'] = site['PROJECT_NAME']
        site_cred['location'] = 'Vancouver'
        site_cred['status'] = 'ACT'

        return self.build_credential_dict(site_credential, site_schema, site_version, site_cred['project_id'], site_cred)


    # generate a site inspection credential
    def generate_inspection_credential(self, site, inspection, mdb_inspection):
        inspection_cred = {}
        inspection_cred['project_id'] = site['PROJECT_ID']
        inspection_cred['inspection_id'] = mdb_inspection['_id']
        inspection_cred['created_date'] = mdb_inspection['createdAt']
        inspection_cred['updated_date'] = mdb_inspection['updatedAt']
        inspection_cred['hash_value'] = mdb_inspection['uploadedHash']

        return self.build_credential_dict(inspc_credential, inspc_schema, inspc_version, 
                                          str(inspection_cred['project_id']) +':' + str(inspection_cred['inspection_id']), 
                                          inspection_cred)


    # get all inspection info from mongo db
    def fetch_mdb_inspection(self, site, inspection):
        mdb_inspection = self.mdb_db['inspections'].find_one( {'_id' : inspection['OBJECT_ID']} )
        mdb_observations = self.mdb_db['observations'].find( {'inspectionId' : inspection['OBJECT_ID']} )
        for mdb_observation in mdb_observations:
            mdb_audios = self.mdb_db['audios'].find_one( {'observationId' : mdb_observation['_id']} )
            mdb_photos = self.mdb_db['photos'].find_one( {'observationId' : mdb_observation['_id']} )
            mdb_videos = self.mdb_db['videos'].find_one( {'observationId' : mdb_observation['_id']} )
            mdb_observation['audios'] = mdb_audios
            mdb_observation['photos'] = mdb_photos
            mdb_observation['videos'] = mdb_videos
        mdb_inspection['observations'] = mdb_observations

        return mdb_inspection


    def generate_all_credentials(self, obj_tree, save_to_db=True):
        creds = []
        try:
            # maintain cursor for storing creds in postgresdb
            cur = self.conn.cursor()

            # hash of sites:
            for site_id in obj_tree:
                site = obj_tree[site_id]

                # issue foundational credential
                cred = self.generate_site_credential(site)
                if save_to_db:
                    self.store_credentials(cur, system_type, cred)
                creds.append(cred)

                # hash of inspections:
                for inspection_id in site['inspections']:
                    inspection = site['inspections'][inspection_id]

                    # fetch inspection report and issue credential
                    mdb_inspection = self.fetch_mdb_inspection(site, inspection)
                    cred = self.generate_inspection_credential(site, inspection, mdb_inspection)
                    if save_to_db:
                        self.store_credentials(cur, system_type, cred)
                    creds.append(cred)

                    # hash of observations:
                    for observation_id in inspection['observations']:
                        observation = inspection['observations'][observation_id]

                        # issue credential for each updated media and observation
                        # TODO just ignore observations for now

                        # audios
                        for audio in observation['audios']:
                            pass
                        
                        # photos
                        for photo in observation['photos']:
                            pass
                        
                        # videos
                        for video in observation['videos']:
                            pass

            self.conn.commit()
            cur.close()
            cur = None

            return creds
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            print(traceback.print_exc())
            raise
        finally:
            if cur is not None:
                cur.close()


    # find all un-processed objects in mongo db
    def find_unprocessed_objects(self):
        unprocessed_objects = []
        for collection in MDB_COLLECTIONS:
            # return if evlocker_date is missing or null
            unprocesseds = self.mdb_db[collection].find( { 'evlocker_date' : None } );
            for unprocessed in unprocesseds:
                todo_obj = {}
                todo_obj['SYSTEM_TYPE_CD'] = system_type
                if collection == 'inspections':
                    todo_obj['PROJECT_ID'] = unprocessed['project']
                    todo_obj['PROJECT_NAME'] = unprocessed['project']
                elif collection == 'observations':
                    todo_obj['observationId'] = unprocessed['_id']
                else:
                    todo_obj['observationId'] = unprocessed['observationId']
                if collection != 'inspections':
                    todo_obj['inspectionId'] = unprocessed['inspectionId']
                todo_obj['COLLECTION_TYPE'] = collection
                todo_obj['OBJECT_ID'] = unprocessed['_id']
                todo_obj['OBJECT_DATE'] = unprocessed['updatedAt']
                todo_obj['UPLOAD_DATE'] = unprocessed['uploadedAt']
                todo_obj['UPLOAD_HASH'] = unprocessed['uploadedHash']
                unprocessed_objects.append(todo_obj)

        # fill in project info for all items
        for unprocessed_object in unprocessed_objects:
            if unprocessed_object['COLLECTION_TYPE'] != 'inspections':
                inspection = self.mdb_db['inspections'].find_one( { '_id' : unprocessed_object['inspectionId'] } );
                unprocessed_object['PROJECT_ID'] = inspection['project']
                unprocessed_object['PROJECT_NAME'] = inspection['project']

        return unprocessed_objects


    def organize_unprocessed_objects(self, mongo_rows):
        organized_objects = {}
        for row in mongo_rows:
            if row['PROJECT_ID'] in organized_objects:
                site_object = organized_objects[row['PROJECT_ID']]
            else:
                site_object = {}
                site_object['PROJECT_ID'] = row['PROJECT_ID']
                site_object['PROJECT_NAME'] = row['PROJECT_NAME']
                site_object['inspections'] = {}
            organized_objects[row['PROJECT_ID']] = site_object

            if row['COLLECTION_TYPE'] == 'inspections':
                inspection_id = row['OBJECT_ID']
            else:
                inspection_id = row['inspectionId']

            if inspection_id in site_object['inspections']:
                inspct_object = site_object['inspections'][row['inspectionId']]
            else:
                inspct_object = {}
                inspct_object['OBJECT_ID'] = inspection_id
                inspct_object['observations'] = {}
            if row['COLLECTION_TYPE'] == 'inspections':
                inspct_object['inspection'] = row
            site_object['inspections'][inspection_id] = inspct_object

            if row['COLLECTION_TYPE'] != 'inspections':
                if row['COLLECTION_TYPE'] == 'observations':
                    observation_id = row['OBJECT_ID']
                else:
                    observation_id = row['observationId']

                if observation_id in inspct_object['observations']:
                    obsrv_object = inspct_object['observations'][observation_id]
                else:
                    obsrv_object = {}
                    obsrv_object['OBJECT_ID'] = observation_id
                    obsrv_object['audios'] = {}
                    obsrv_object['photos'] = {}
                    obsrv_object['videos'] = {}
                if row['COLLECTION_TYPE'] == 'observations':
                    obsrv_object['observation'] = row
                inspct_object['observations'][observation_id] = obsrv_object

                if row['COLLECTION_TYPE'] != 'observations':
                    if row['OBJECT_ID'] in obsrv_object[row['COLLECTION_TYPE']]:
                        media_object = obsrv_object[row['COLLECTION_TYPE']][row['OBJECT_ID']]
                    else:
                        media_object = {}
                        media_object['OBJECT_ID'] = row['OBJECT_ID']
                        media_object['media_type'] = row['COLLECTION_TYPE']
                    media_object['media'] = row
                    obsrv_object[row['COLLECTION_TYPE']][row['OBJECT_ID']] = media_object

        return organized_objects


    # process inbound data from the mongodb inspections database
    def process_event_queue(self):
        cur = None
        start_time = time.perf_counter()
        processing_time = 0
        max_processing_time = 10 * 60
        continue_loop = True
        max_batch_size = CORP_BATCH_SIZE
        saved_creds = 0

        # find all un-processed objects from mongodb
        mongo_rows = self.find_unprocessed_objects()
        print("Row count = ", len(mongo_rows))

        # organize by project/inspection/observation
        mongo_objects = self.organize_unprocessed_objects(mongo_rows)
        print("Object count = ", len(mongo_objects))

        # generate and save credentials
        creds = self.generate_all_credentials(mongo_objects)
        print("Generated cred count = ", len(creds))


    def display_event_processing_status(self):
        tables = ['event_history_log', 'credential_log']

        for table in tables:
            process_ct     = self.get_record_count(table, False)
            outstanding_ct = self.get_record_count(table, True)
            print('Table:', table, 'Processed:', process_ct, 'Outstanding:', outstanding_ct)

            sql = "select count(*) from " + table + " where process_success = 'N'"
            error_ct = self.get_sql_record_count(sql)
            print('      ', table, 'Process Errors:', error_ct)
            if 0 < error_ct:
                self.print_processing_errors(table)

    def get_outstanding_corps_record_count(self):
        return self.get_record_count('event_by_corp_filing')
        
    def get_outstanding_creds_record_count(self):
        return self.get_record_count('credential_log')
        
    def get_record_count(self, table, unprocessed=True):
        sql_ct_select = 'select count(*) from'
        sql_corp_ct_processed   = 'where process_date is not null'
        sql_corp_ct_outstanding = 'where process_date is null'

        if table == 'credential_log':
            sql_corp_ct_processed = sql_corp_ct_processed

        sql = sql_ct_select + ' ' + table + ' ' + (sql_corp_ct_outstanding if unprocessed else sql_corp_ct_processed)

        return self.get_sql_record_count(sql)

    def get_sql_record_count(self, sql):
        cur = None
        try:
            cur = self.conn.cursor()
            cur.execute(sql)
            ct = cur.fetchone()[0]
            cur.close()
            cur = None
            return ct
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            print(traceback.print_exc())
            raise
        finally:
            if cur is not None:
                cur.close()
            cur = None

    def print_processing_errors(self, table):
        sql = """select * from """ + table + """
                 where process_success = 'N'
                 order by process_date DESC
                 limit 20"""
        rows = self.get_sql_rows(sql)
        print("       Recent errors:")
        print(rows)

    def get_sql_rows(self, sql):
        cursor = None
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql)
            desc = cursor.description
            column_names = [col[0] for col in desc]
            rows = [dict(zip(column_names, row))  
                for row in cursor]
            cursor.close()
            cursor = None
            return rows
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            print(traceback.print_exc())
            raise
        finally:
            if cursor is not None:
                cursor.close()
            cursor = None


