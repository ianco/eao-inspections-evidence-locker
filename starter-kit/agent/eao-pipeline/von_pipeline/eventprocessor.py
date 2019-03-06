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

MDB_COLLECTIONS = ['Inspection','Observation','Audio','Photo','Video']

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
            self.mdb_client = MongoClient('mongodb://%s:%s@%s:%s/%s' % (mdb_config['user'], mdb_config['password'], mdb_config['host'], mdb_config['port'], mdb_config['database']))
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
                COLLECTION VARCHAR(255) NOT NULL,
                OBJECT_DATE TIMESTAMP NOT NULL,
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
                COLLECTION VARCHAR(255) NOT NULL,
                PROJECT_ID VARCHAR(255) NOT NULL,
                PROJECT_NAME VARCHAR(255) NOT NULL,
                OBJECT_ID VARCHAR(255) NOT NULL,
                OBJECT_DATE TIMESTAMP NOT NULL,
                UPLOAD_DATE TIMESTAMP,
                UPLOAD_HASH VARCHAR(255),
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
                SOURCE_COLLECTION VARCHAR(255) NOT NULL,
                SOURCE_ID VARCHAR(255) NOT NULL,
                PROJECT_ID VARCHAR(255) NOT NULL,
                PROJECT_NAME VARCHAR(255) NOT NULL,
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
    def insert_processed_event(self, system_type, collection, object_date):
        """ insert a new event into the event table """
        sql = """INSERT INTO LAST_EVENT (SYSTEM_TYPE_CD, COLLECTION, OBJECT_DATE, ENTRY_DATE)
                 VALUES(%s, %s, %s, %s) RETURNING RECORD_ID;"""
        cur = None
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (system_type, collection, object_date, datetime.datetime.now(),))
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

    # get the id of the last event processed (of a specific collection)
    def get_last_processed_event(self, system_type, collection):
        cur = None
        try:
            cur = self.conn.cursor()
            cur.execute("""SELECT RECORD_ID, SYSTEM_TYPE_CD, COLLECTION, OBJECT_DATE, ENTRY_DATE
                           FROM LAST_EVENT where SYSTEM_TYPE_CD = %s and COLLECTION = %s
                           ORDER BY OBJECT_DATE desc""", (system_type, collection,))
            row = cur.fetchone()
            cur.close()
            cur = None
            event = None
            if row is not None:
                event = {}
                event['RECORD_ID'] = row[0]
                event['SYSTEM_TYPE_CD'] = row[1]
                event['COLLECTION'] = row[2]
                event['OBJECT_DATE'] = row[3]
                event['ENTRY_DATE'] = row[4]
            return event
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
            cur.execute("""SELECT max(object_date) FROM LAST_EVENT where SYSTEM_TYPE_CD = %s""", (system_type,))
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

    # insert data for one corp into the history table
    def insert_inspection_history(self, cur, system_type, collection, project_id, project_name, object_id, object_date, upload_date, upload_hash, process_date=None, process_success=None, process_msg=None):
        """ insert a new corps into the corps table """
        sql = """INSERT INTO EVENT_HISTORY_LOG 
                 (SYSTEM_TYPE_CD, COLLECTION, PROJECT_ID, PROJECT_NAME, OBJECT_ID, OBJECT_DATE, UPLOAD_DATE, UPLOAD_HASH, ENTRY_DATE,
                    PROCESS_DATE, PROCESS_SUCCESS, PROCESS_MSG)
                 VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING RECORD_ID;"""
        if process_date is None:
            process_date = datetime.datetime.now()
        if process_success is None:
            process_success = 'Y'
        if process_msg is None:
            process_msg = ''
        cur.execute(sql, (system_type, collection, project_id, project_name, object_id, object_date, upload_date, upload_hash, datetime.datetime.now(), process_date, process_success, process_msg))
        record_id = cur.fetchone()[0]
        return record_id

    # insert a generated JSON credential into our log
    def insert_json_credential(self, cur, system_cd, cred_type, cred_id, schema_name, schema_version, credential, source_collection, source_id, project_id, project_name):
        sql = """INSERT INTO CREDENTIAL_LOG (SYSTEM_TYPE_CD, CREDENTIAL_TYPE_CD, CREDENTIAL_ID, 
                SCHEMA_NAME, SCHEMA_VERSION, CREDENTIAL_JSON, CREDENTIAL_HASH, ENTRY_DATE, SOURCE_COLLECTION, SOURCE_ID, PROJECT_ID, PROJECT_NAME)
                VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING RECORD_ID;"""
        # create row(s) for corp creds json info
        cred_json = json.dumps(credential, cls=CustomJsonEncoder, sort_keys=True)
        cred_hash = hashlib.sha256(cred_json.encode('utf-8')).hexdigest()
        try:
            cur.execute("savepoint save_" + cred_type)
            cur.execute(sql, (system_cd, cred_type, cred_id, schema_name, schema_version, cred_json, cred_hash, datetime.datetime.now(), source_collection, source_id, project_id, project_name))
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
    def store_credentials(self, cur, system_typ_cd, corp_cred, source_collection, source_id, project_id, project_name):
        cred_count = 0
        cred_count = cred_count + self.insert_json_credential(cur, system_typ_cd, corp_cred['cred_type'], corp_cred['id'], 
                                                        corp_cred['schema'], corp_cred['version'], corp_cred['credential'],
                                                        source_collection, source_id, project_id, project_name)
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
        site_cred['entity_status'] = 'ACT'

        return self.build_credential_dict(site_credential, site_schema, site_version, site_cred['project_id'], site_cred)


    # find an (existing) credential for the site
    def find_site_credential(self, site):
        cur = None
        try:
            cur = self.conn.cursor()
            cur.execute("""SELECT PROJECT_ID, PROJECT_NAME FROM CREDENTIAL_LOG 
                           where SYSTEM_TYPE_CD = %s and PROJECT_ID = %s and CREDENTIAL_TYPE_CD = %s""", 
                           (system_type, site['PROJECT_ID'], site_credential,))
            row = cur.fetchone()
            cur.close()
            cur = None
            if row is None:
                return None
            site_cred = {}
            site_cred['project_id'] = row[0]
            site_cred['project_name'] = row[1]
            return site_cred
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            print(traceback.print_exc())
            raise
        finally:
            if cur is not None:
                cur.close()


    # generate a site inspection credential
    def generate_inspection_credential(self, site, inspection, mdb_inspection):
        inspection_cred = {}
        inspection_cred['project_id'] = site['PROJECT_ID']
        inspection_cred['inspection_id'] = mdb_inspection['_id']
        inspection_cred['created_date'] = mdb_inspection['_created_at']
        inspection_cred['updated_date'] = mdb_inspection['_updated_at']
        inspection_cred['hash_value'] = mdb_inspection['_uploaded_hash'] if '_uploaded_hash' in mdb_inspection else None

        return self.build_credential_dict(inspc_credential, inspc_schema, inspc_version, 
                                          str(inspection_cred['project_id']) +':' + str(inspection_cred['inspection_id']), 
                                          inspection_cred)


    # get all inspection info from mongo db
    def fetch_mdb_inspection(self, site, inspection):
        mdb_inspection = self.mdb_db['Inspection'].find_one( {'_id' : inspection['OBJECT_ID']} )
        mdb_observations = self.mdb_db['Observation'].find( {'inspectionId' : inspection['OBJECT_ID']} )
        for mdb_observation in mdb_observations:
            mdb_audios = self.mdb_db['Audio'].find_one( {'observationId' : mdb_observation['_id']} )
            mdb_photos = self.mdb_db['Photo'].find_one( {'observationId' : mdb_observation['_id']} )
            mdb_videos = self.mdb_db['Video'].find_one( {'observationId' : mdb_observation['_id']} )
            mdb_observation['Audio'] = mdb_audios
            mdb_observation['Photo'] = mdb_photos
            mdb_observation['Video'] = mdb_videos
        mdb_inspection['Observation'] = mdb_observations

        return mdb_inspection


    def max_collection_date(self, max_dates, collection, inspection_date):
        if not collection in max_dates:
            return inspection_date
        if inspection_date > max_dates[collection]:
            return inspection_date
        return max_dates[collection]


    def generate_all_credentials(self, obj_tree, save_to_db=True):
        creds = []
        max_dates = {}
        try:
            # maintain cursor for storing creds in postgresdb
            cur = self.conn.cursor()

            # hash of sites:
            for site_id in obj_tree:
                site = obj_tree[site_id]

                # hash of inspections:
                for inspection_id in site['inspections']:
                    inspection = site['inspections'][inspection_id]
                    i_d = inspection['inspection']

                    if save_to_db:
                        inspection_rec_id = self.insert_inspection_history(cur, system_type, 'Inspection', i_d['PROJECT_ID'], i_d['PROJECT_NAME'], i_d['OBJECT_ID'], i_d['OBJECT_DATE'], i_d['UPLOAD_DATE'], i_d['UPLOAD_HASH'])

                    # issue foundational credential / only if we don't have one yet
                    site_cred = self.find_site_credential(site)
                    if site_cred is None:
                        site_cred = self.generate_site_credential(site)
                        if save_to_db:
                            self.store_credentials(cur, system_type, site_cred, 'Inspection', inspection_rec_id, i_d['PROJECT_ID'], i_d['PROJECT_NAME'])
                        creds.append(site_cred)

                    # fetch inspection report and issue credential
                    mdb_inspection = self.fetch_mdb_inspection(site, inspection)
                    cred = self.generate_inspection_credential(site, inspection, mdb_inspection)
                    if save_to_db:
                        self.store_credentials(cur, system_type, cred, 'Inspection', inspection_rec_id, i_d['PROJECT_ID'], i_d['PROJECT_NAME'])
                    creds.append(cred)
                    max_dates['Inspection'] = self.max_collection_date(max_dates, 'Inspection', mdb_inspection['_updated_at'])

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

            # record max dates processed
            if save_to_db:
                for collection in max_dates:
                    self.insert_processed_event(system_type, collection, max_dates[collection])
                
            return creds
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            print(traceback.print_exc())
            raise
        finally:
            if cur is not None:
                cur.close()


    # derive a project id from a name (determanistic)
    def project_name_to_id(self, project_name):
        # first 10 non-space chars
        subname = "".join(project_name.split()).upper()
        if 12 >= len(subname):
            return subname
        return subname[:12]


    # find all un-processed objects in mongo db
    def find_unprocessed_objects(self):
        unprocessed_objects = []

        # TODO for now just look at the Investigations collection ...
        for collection in [MDB_COLLECTIONS[0],]:
            # find last processed date for this collection
            last_event = self.get_last_processed_event(system_type, collection)

            # return if evlocker_date is missing or null
            if last_event is None:
                unprocesseds = self.mdb_db[collection].find( { 'evlocker_date' : { "$exists" : False } } )
            else:
                last_date = last_event['OBJECT_DATE']
                unprocesseds = self.mdb_db[collection].find( {'$and': [{'evlocker_date': {"$exists": False}}, {'_updated_at': {"$gt": last_date}}]} )

            # fetch unprocessed records
            for unprocessed in unprocesseds:
                todo_obj = {}
                todo_obj['SYSTEM_TYPE_CD'] = system_type
                if collection == 'Inspection':
                    todo_obj['PROJECT_ID'] = self.project_name_to_id(unprocessed['project'])
                    todo_obj['PROJECT_NAME'] = unprocessed['project']
                elif collection == 'Observation':
                    todo_obj['observationId'] = unprocessed['_id']
                else:
                    todo_obj['observationId'] = unprocessed['observationId'] if 'observationId' in unprocessed else None
                if collection != 'Inspection':
                    todo_obj['inspectionId'] = unprocessed['inspectionId'] if 'inspectionId' in unprocessed else None
                todo_obj['COLLECTION'] = collection
                todo_obj['OBJECT_ID'] = unprocessed['_id']
                todo_obj['OBJECT_DATE'] = unprocessed['_updated_at']
                todo_obj['UPLOAD_DATE'] = unprocessed['_uploaded_at'] if '_uploaded_at' in unprocessed else None
                todo_obj['UPLOAD_HASH'] = unprocessed['_uploaded_hash'] if '_uploaded_hash' in unprocessed else None
                unprocessed_objects.append(todo_obj)

        # fill in project info for all items
        for unprocessed_object in unprocessed_objects:
            if unprocessed_object['COLLECTION'] != 'Inspection' and 'inspectionId' in unprocessed_object:
                inspection = self.mdb_db['Inspection'].find_one( { '_id' : unprocessed_object['inspectionId'] } );
                if inspection is not None:
                    unprocessed_object['PROJECT_ID'] = inspection['project']
                    unprocessed_object['PROJECT_NAME'] = inspection['project']

        return unprocessed_objects


    def organize_unprocessed_objects(self, mongo_rows):
        organized_objects = {}
        for row in mongo_rows:
            if 'PROJECT_ID' in row:
                if row['PROJECT_ID'] in organized_objects:
                    site_object = organized_objects[row['PROJECT_ID']]
                else:
                    site_object = {}
                    site_object['PROJECT_ID'] = row['PROJECT_ID']
                    site_object['PROJECT_NAME'] = row['PROJECT_NAME']
                    site_object['inspections'] = {}
                organized_objects[row['PROJECT_ID']] = site_object

                if row['COLLECTION'] == 'Inspection':
                    inspection_id = row['OBJECT_ID']
                elif 'inspectionId' in row:
                    inspection_id = row['inspectionId']
                else:
                    inspection_id = None

                if inspection_id is not None:
                    if inspection_id in site_object['inspections']:
                        inspct_object = site_object['inspections'][inspection_id]
                    else:
                        inspct_object = {}
                        inspct_object['OBJECT_ID'] = inspection_id
                        inspct_object['observations'] = {}
                    if row['COLLECTION'] == 'Inspection':
                        inspct_object['inspection'] = row
                    site_object['inspections'][inspection_id] = inspct_object

                    if row['COLLECTION'] != 'Inspection':
                        if row['COLLECTION'] == 'Observation':
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
                        if row['COLLECTION'] == 'Observation':
                            obsrv_object['observation'] = row
                        inspct_object['observations'][observation_id] = obsrv_object

                        if row['COLLECTION'] != 'Observation':
                            if row['OBJECT_ID'] in obsrv_object[row['COLLECTION']]:
                                media_object = obsrv_object[row['COLLECTION']][row['OBJECT_ID']]
                            else:
                                media_object = {}
                                media_object['OBJECT_ID'] = row['OBJECT_ID']
                                media_object['media_type'] = row['COLLECTION']
                            media_object['media'] = row
                            obsrv_object[row['COLLECTION']][row['OBJECT_ID']] = media_object

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


