import sys

from multiremodnav.call_remodnav import call_remodnav

if __name__ == '__main__':
    # Load the arguments
    participant_id = sys.argv[1]
    measurement_moment = sys.argv[2]
    task = sys.argv[3]

    batch_id = ''
    if(len(sys.argv) > 3 + 1):
        batch_id = sys.argv[4]

    call_remodnav(participant_id, measurement_moment, task, batch_id)