import sys, subprocess, os
from datetime import datetime
sys.path.append('../../')
import __constants
from helpers.logger import logger

def call_remodnav(participant_id, measurement_moment, task, batch_id = ''):
    output_folder = __constants.output_folder
    input_folder = __constants.input_folder

    logger.info('Calling REMODNAV')
    logger.info("- Participant number: {}".format(participant_id))
    logger.info("- Measurement moment: {}".format(measurement_moment))
    logger.info("- Task: {}".format(task))

    logger.info('STEPS')

    # Config
    now = datetime.now()
    date_string = f'{now.strftime("%Y-%m-%d_%H-%M-%S")}_{batch_id}'
    input_folder_participant = f'{input_folder}/{participant_id}/{measurement_moment}/{task}'
    output_folder_participant = f'{output_folder}/{participant_id}/{measurement_moment}/{task}'

    # Prepare the data
    logger.info('- Calling prepare.py')
    subprocess.call(['python3', './multiremodnav/prepare.py', input_folder_participant])

    # Make the output folder
    if not os.path.exists(output_folder_participant):
        os.makedirs(output_folder_participant)
        logger.info('- Created output folder')
    else:
        logger.info('- Output folder already existed')

    # Call our REMODNAV adaptation
    logger.info('- Calling REMODNAV')
    tsv_file = f"{input_folder_participant}/gp.tsv"
    events_file = f"{output_folder_participant}/events_{date_string}.tsv"

    subprocess.call(['python3',
                        './remodnav-adaptation/__init__.py',
                        tsv_file,
                        events_file,
                        '240',
                        '--min-blink-duration=0.075',
                        '--dilate-nan=0',
                        f'--savgol-length={(21/240)}',
                        '--pursuit-velthresh=50.0',
                        '--noise-factor=3.0', #'--noise-factor=5.0',
                        '--min-pursuit-duration=1000'])
    logger.info('- Done calling REMODNAV')

    # REPORT.PY
    logger.info('- Calling report report.py')
    subprocess.call([
        'python3', './multiremodnav/report.py', f'{output_folder_participant}/events_{date_string}',
        participant_id,measurement_moment,task
    ])
    logger.info('- Done calling REMODNAV')

if __name__ == '__main__':
    # Load the arguments
    participant_id = sys.argv[1]
    measurement_moment = sys.argv[2]
    task = sys.argv[3]

    call_remodnav(participant_id, measurement_moment, task)