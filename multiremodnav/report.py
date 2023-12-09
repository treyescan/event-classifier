import sys, json
import pandas as pd
import matplotlib.pyplot as plt

# Helper to conviently generate descriptive values based on input df
def compute_description(label, new_key, data):
    return_dict = {}
    return_dict[f'{new_key}_mean'] = data['mean'][label]
    return_dict[f'{new_key}_std'] = data['std'][label]
    return_dict[f'{new_key}_min'] = data['min'][label]
    return_dict[f'{new_key}_25'] = data['25%'][label]
    return_dict[f'{new_key}_50'] = data['50%'][label]
    return_dict[f'{new_key}_75'] = data['75%'][label]
    return_dict[f'{new_key}_max'] = data['max'][label]
    return return_dict

# Load events
basename = sys.argv[1]
participant_id = sys.argv[2]
measurement_moment = sys.argv[3]
task_id = sys.argv[4]

txt_file = '{}.txt'.format(basename)
events_agg_file = '{}_agg.json'.format(basename)
events_file = '{}.tsv'.format(basename)
image_file = '{}.png'.format(basename)
hist_image_file = '{}_hist.png'.format(basename)

events = pd.read_csv(events_file, sep='\t', header=0)
counts = events['label'].value_counts()

sacc = events.loc[events['label'] == 'SACC']

sacc_amps = sacc['amp'].to_numpy()
plt.hist(sacc_amps, bins=40)
plt.ylabel('# of saccades')
plt.xlabel('degrees')
plt.savefig(hist_image_file)

agg_to_save = {}
with open(txt_file, 'a') as f:
    f.write('\n\n')

    for label, count in counts.items():
        agg_to_save[label] = count
        f.write('{}: {}'.format(label, count))
        f.write('\n')

# calculate these and add them to agg_to_save 
# after which they will be automatically added to the merged remodnav output

# combine ISAC and SACC 
events.loc[events["label"] == 'SACC', "label"] = 'ISACC'
events.loc[events["label"] == 'ISAC', "label"] = 'ISACC'

# Save count of ISACC
# and caculate mean, std, median of amp ISACC
data = events.groupby('label')['amp'].describe()
agg_to_save['ISACC'] = data['count']['ISACC']
agg_to_save = agg_to_save | compute_description('ISACC', 'ISACC_amp', data)

# Calculate bins of ISACC
groups = events.groupby(['label', pd.cut(events.amp, range(0, 110, 5))])
unstacked = groups.size().unstack()
isac_sacc_bins = unstacked.loc[['ISACC']].stack()

for bin, value in isac_sacc_bins['ISACC'].items():
    agg_to_save[f'ISACC_bin_{bin}'] = value

# Calculage mean, std, median of avg_vel ISACC
data = events.groupby('label')['avg_vel'].describe()
agg_to_save = agg_to_save | compute_description('ISACC', 'ISACC_avg_vel', data)

# Calculage mean, std, median of peak_vel ISACC
data = events.groupby('label')['peak_vel'].describe()
agg_to_save = agg_to_save | compute_description('ISACC', 'ISACC_peak_vel', data)

# Calculage mean, std, median of med_vel ISACC
data = events.groupby('label')['med_vel'].describe()
agg_to_save = agg_to_save | compute_description('ISACC', 'ISACC_med_vel', data)

# Number of saccades up, down, left, right
ISACC_events = events[events['label'] == 'ISACC']
agg_to_save['ISACC_left'] = len(ISACC_events[ISACC_events['start_x'] > ISACC_events['end_x']]) # links
agg_to_save['ISACC_right'] = len(ISACC_events[ISACC_events['start_x'] < ISACC_events['end_x']]) # rechts
agg_to_save['ISACC_down'] = len(ISACC_events[ISACC_events['start_y'] > ISACC_events['end_y']]) # beneden
agg_to_save['ISACC_up'] = len(ISACC_events[ISACC_events['start_y'] < ISACC_events['end_y']]) # boven

# Number of ISACC saccades with amplitudes smaller than 1 degree
isacc_micro_amp1 = ISACC_events[ISACC_events['amp'] < 1]
agg_to_save['ISACC_micro_amp1_count'] = len(isacc_micro_amp1)

with open(events_agg_file, "w") as events_agg_file:
    agg_to_save['participant_id'] = participant_id
    agg_to_save['measurement_moment'] = measurement_moment
    agg_to_save['task_id'] = task_id
    json.dump(agg_to_save, events_agg_file, indent = 4) 

print('\nOutputted to {}'.format(events_file))
print('Image saved to {}'.format(image_file))
print('Histogram Image saved to {}'.format(hist_image_file))
print('Report saved to {}\n'.format(txt_file))

f = open(txt_file, 'r')
file_contents = f.read()
print(file_contents)
f.close()

print('To overlay, run: python3 overlay.py ./path_to_gp.csv {} {} ./path_to_video.mp4 0'.format(
    events_file, image_file
))