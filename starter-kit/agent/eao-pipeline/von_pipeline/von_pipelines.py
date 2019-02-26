from data_integration.pipelines import Pipeline, Task
from data_integration.commands.python import ExecutePython

def von_root_pipeline():

    parent_pipeline = Pipeline(
        id = 'holder_for_pipeline_versions',
        description = 'Holder for the different versions of the VON Data Pipeline.')

    parent_pipeline.add(von_data_pipeline())
    parent_pipeline.add(von_data_pipeline_status())

    init_pipeline = Pipeline(
        id = 'initialization_and_load_tasks',
        description = 'One-time initialization and data load tasks')

    init_pipeline.add(db_init_pipeline())
    init_pipeline.add(von_data_pipeline_initial_load())
    init_pipeline.add(von_data_pipeline_post_credentials())

    parent_pipeline.add(init_pipeline)

    test_pipeline = Pipeline(
        id = 'test_and_demo_tasks',
        description = 'Holder for test and demo tasks.')

    test_pipeline.add(von_data_init_test_data())
    test_pipeline.add(von_data_test_registrations())
    test_pipeline.add(von_data_pipeline_single_thread())

    parent_pipeline.add(test_pipeline)

    return parent_pipeline

def von_data_pipeline():
    import von_pipeline

    pipeline1 = Pipeline(
        id='von_data_event_processor',
        description='A pipeline that processes von_data events and generates credentials.')

    sub_pipeline1_2 = Pipeline(id='load_and_process_von_data_data', description='Load von_data data and generate credentials')
    sub_pipeline1_2.add(Task(id='register_un_processed_events', description='Register un-processed events',
                          commands=[ExecutePython('./von_pipeline/find-unprocessed-events.py')]))
    sub_pipeline1_2.add(Task(id='load_von_data_data', description='Load von_data data',
                          commands=[ExecutePython('./von_pipeline/process-corps-generate-creds.py')]), ['register_un_processed_events'])
    sub_pipeline1_2.add(Task(id='create_von_data_credentials', description='Create credentials',
                          commands=[ExecutePython('./von_pipeline/generate-creds.py')]), ['load_von_data_data'])
    pipeline1.add(sub_pipeline1_2)

    sub_pipeline1_3 = Pipeline(id='submit_von_data_credentials', description='Submit von_data credentials to P-X')
    sub_pipeline1_3.add(Task(id='submit_credentials', description='Submit credentials',
                          commands=[ExecutePython('./von_pipeline/submit-creds.py')]))
    pipeline1.add(sub_pipeline1_3, ['load_and_process_von_data_data'])

    return pipeline1

def von_data_pipeline_single_thread():
    import von_pipeline

    pipeline1 = Pipeline(
        id='von_data_pipeline_single_thread',
        description='A pipeline that processes von_data events and generates credentials.')

    sub_pipeline1_2 = Pipeline(id='load_and_process_von_data_data_single_thread', description='Load von_data data and generate credentials')
    sub_pipeline1_2.add(Task(id='register_un_processed_events_single_thread', description='Register un-processed events',
                          commands=[ExecutePython('./von_pipeline/find-unprocessed-events.py')]))
    sub_pipeline1_2.add(Task(id='load_von_data_data_single_thread', description='Load von_data data',
                          commands=[ExecutePython('./von_pipeline/register_un_processed_events')]), ['register_un_processed_events_single_thread'])
    pipeline1.add(sub_pipeline1_2)

    sub_pipeline1_3 = Pipeline(id='submit_von_data_credentials_single_thread', description='Submit von_data credentials to P-X')
    sub_pipeline1_3.add(Task(id='submit_credentials_single_thread', description='Submit credentials',
                          commands=[ExecutePython('./von_pipeline/submit-creds-single-thread.py')]))
    pipeline1.add(sub_pipeline1_3, ['load_and_process_von_data_data_single_thread'])

    return pipeline1

def von_data_pipeline_initial_load():
    import von_pipeline

    pipeline1 = Pipeline(
        id='von_data_corp_loader',
        description='A pipeline that does the initial data load and credentials for all corporations.')

    sub_pipeline1_2 = Pipeline(id='load_and_process_von_data_corps', description='Load von_data and generate credentials')
    sub_pipeline1_2.add(Task(id='register_un_processed_corps', description='Register un-processed active corps',
                          commands=[ExecutePython('./von_pipeline/find-unprocessed-corps_actve.py')]))
    sub_pipeline1_2.add(Task(id='load_von_data_data_a', description='Load von_data data',
                          commands=[ExecutePython('./von_pipeline/process-corps-generate-creds.py')]), ['register_un_processed_corps'])
    pipeline1.add(sub_pipeline1_2)

    return pipeline1

def von_data_pipeline_post_credentials():
    import von_pipeline

    pipeline1 = Pipeline(
        id='von_data_credential_poster',
        description='A pipeline that posts generated credentials to TOB.')

    sub_pipeline1_3 = Pipeline(id='submit_von_data_credentials_a', description='Submit von_data credentials to P-X')
    sub_pipeline1_3.add(Task(id='submit_credentials_a', description='Submit credentials',
                          commands=[ExecutePython('./von_pipeline/submit-creds.py')]))
    pipeline1.add(sub_pipeline1_3)

    return pipeline1

def von_data_pipeline_status():
    import von_pipeline

    pipeline = Pipeline(
        id='von_data_pipeline_status',
        description='Display overall event processing status.')

    pipeline.add(Task(id='display_pipeline_status', description='Display status of the overall pipeline processing status',
                        commands=[ExecutePython('./von_pipeline/display_pipeline_status.py')]))

    return pipeline

def db_init_pipeline():
    import von_pipeline

    pipeline = Pipeline(
      id = 'von_data_db_init',
      description = 'Initialize von_data Event Processor database')

    pipeline.add(Task(id='create_tables', description='Create event processing tables',
                        commands=[ExecutePython('./von_pipeline/create.py')]))
    pipeline.add(Task(id='initialize_tables', description='Insert configuration data',
                        commands=[ExecutePython('./von_pipeline/insert.py')]), ['create_tables'])

    return pipeline

def von_data_init_test_data():
    import von_pipeline

    pipeline = Pipeline(
        id='von_data_init_test_data',
        description='A pipeline that initializes event processor database for testing.')

    pipeline.add(Task(id='register_test_corps', description='Insert some test data for processing',
                        commands=[ExecutePython('./von_pipeline/insert-test.py')]))

    return pipeline

def von_data_test_registrations():
    import von_pipeline

    pipeline = Pipeline(
        id='von_data_test_registrations',
        description='A pipeline that queues up a small set of test corporations.')

    pipeline.add(Task(id='register_test_corps', description='Register some test corps for processing',
                        commands=[ExecutePython('./von_pipeline/find-test-corps.py')]))

    return pipeline
