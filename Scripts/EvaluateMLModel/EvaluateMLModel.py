import numpy as np
import pandas as pd
from sklearn.metrics import precision_score, recall_score
from tabulate import tabulate

from CommonServerPython import *


def binarize(arr, threshold):
    return np.where(arr >= threshold, 1.0, 0)


def calculate_confusion_matrix(y_true, y_pred, y_pred_per_class, threshold):
    indices_higher_than_threshold = set()
    for i, y in enumerate(y_pred):
        if y_pred_per_class[y][i] >= threshold:
            indices_higher_than_threshold.add(i)

    y_true_at_threshold = [y for i, y in enumerate(y_true) if i in indices_higher_than_threshold]
    y_pred_at_threshold = [y for i, y in enumerate(y_pred) if i in indices_higher_than_threshold]
    data = {'y_true': y_true_at_threshold,
            'y_pred': y_pred_at_threshold,
            }
    df = pd.DataFrame(data, columns=['y_true', 'y_pred'])
    csr_matrix = pd.crosstab(df['y_true'], df['y_pred'], rownames=['True'], colnames=['Predicted'], margins=True)
    return csr_matrix


def generate_metrics_df(y_true, y_true_per_class, y_pred, y_pred_per_class, threshold):
    df = pd.DataFrame(columns=['Class', 'Precision', 'Recall', 'Correct Classifications', 'Coverage', 'Below Threshold',
                               'Total'])
    for class_ in sorted(y_pred_per_class):
        y_pred_class = y_pred_per_class[class_]
        y_true_class = y_true_per_class[class_]
        y_pred_class_binary = binarize(y_pred_class, threshold)
        precision = precision_score(y_true=y_true_class, y_pred=y_pred_class_binary)
        recall = recall_score(y_true=y_true_class, y_pred=y_pred_class_binary)
        classified_correctly = sum(1 for y_true_i, y_pred_i in zip(y_true_class, y_pred_class_binary) if y_true_i == 1
                                   and y_pred_i == 1)
        above_thresh = sum(1 for i, y_true_i in enumerate(y_true_class) if y_true_i == 1
                           and any(y_pred_per_class[c][i] >= threshold for c in y_pred_per_class))
        total = int(sum(y_true_class))
        df = df.append({'Class': class_,
                        'Precision': precision,
                        'Recall': recall,
                        'Correct Classifications': classified_correctly,
                        'CoverageInt': int(above_thresh),
                        'Total': total}, ignore_index=True)
    df = df.append({'Class': 'All',
                    'Precision': df["Precision"].mean(),
                    'Recall': df["Recall"].mean(),
                    'Correct Classifications': df["Correct Classifications"].sum(),
                    'CoverageInt': df["CoverageInt"].sum(),
                    'Total': df["Total"].sum()}, ignore_index=True)
    df['Precision'] = df['Precision'].apply(lambda precision: '{:.1f}%'.format(precision * 100))
    df['Recall'] = df['Recall'].apply(lambda recall: '{:.1f}%'.format(recall * 100))
    df['Coverage'] = df.apply(lambda row: '{:.1f}% ({}/{})'.format(float(row['CoverageInt']) * 100 / row['Total'],
                                                                   int(row['CoverageInt']), row['Total']), axis=1)
    explanation = [
        'Precision - binary precision of the class (correct classificationss of the class, \
        divided by number of mails in the evaluation set which were classified as this class by the model',
        'Recall - binary recall of the class (correct Classificationss of the class, divided by number of mails in \
         the evaluation set which are labeled as this class of the evaluation set',
        'Correct Classifications - number of mails from the class in the evaluation set which were correct \
        classifications',
        'Coverage -  number of mails from the class in the evaluation set which their prediction was at a \
        higher confidence than threshold',
        'Total - The number of mails from the class in the evaluation set (above and below threshold)',

    ]
    df.set_index('Class', inplace=True)
    return df, explanation


def output_report(y_true, y_true_per_class, y_pred, y_pred_per_class, threshold):
    csr_matrix_at_threshold = calculate_confusion_matrix(y_true, y_pred, y_pred_per_class, threshold)
    metrics_df, metrics_explanation = generate_metrics_df(y_true, y_true_per_class, y_pred, y_pred_per_class, threshold)
    coverage = metrics_df.loc[['All']]['CoverageInt'][0]
    test_set_size = metrics_df.loc[['All']]['Total'][0]

    human_readable_title = ['## Model Evaluation']
    human_readable_threshold = [
        '### Summary',
        '- Probability threshold of {:.1f} meets the conditions of required precision and recall.'.format(threshold),
        '- {}/{} mails of the evaluation set were predicted with a higher confidence than this threshold.'.format(
            int(coverage), int(test_set_size)),
        '- The rest {}/{} mails of the evaluation set were predicted with a lower confidnece than this \
        threshold (thus these predictions were ignored).'.format(
            int(test_set_size - coverage), int(test_set_size)),
        '- (Total of {} mails in the evaluation set)'.format(int(test_set_size)),
        '- Expected coverage ratio: the model will be able to provide a prediction for {:.2f}% of mails in \
        traffic ({}/{})'.format(
            coverage / test_set_size * 100, int(coverage), int(test_set_size)),
        '- Evaluation of the model performance using this probability threshold can be found below:']
    metrics_df.drop(columns=['CoverageInt'], inplace=True)
    pd.set_option('display.max_columns', None)

    tablualted_csr = tabulate(metrics_df, tablefmt="pipe", headers="keys")
    class_metrics_human_readable = ['### Metrics per Class', tablualted_csr, '#### Metrics Explanation']
    class_metrics_human_readable += ['- ' + row for row in metrics_explanation]

    csr_matrix_readable = ['Confusion Matrix for Evaluation Set above Confidence Threshold:',
                           tabulate(csr_matrix_at_threshold,
                                    tablefmt="pipe",
                                    headers="keys").replace("True", "True \\ Predicted")]
    human_readable = human_readable_title + ['\n']
    human_readable += human_readable_threshold + ['\n']
    human_readable += class_metrics_human_readable + ['\n']
    human_readable += csr_matrix_readable
    contents = {'threshold': threshold, 'csr_matrix_at_threshold': csr_matrix_at_threshold, 'metrics_df': metrics_df}
    entry = {
        'Type': entryTypes['note'],
        'Contents': contents,
        'ContentsFormat': formats['json'],
        'HumanReadable': human_readable,
        'HumanReadableFormat': formats['markdown'],
    }
    return entry


def find_threshold(y_true_str, y_pred_str, target_precision, target_recall):
    y_true = convert_str_to_json(y_true_str, 'yTrue')
    y_pred_all_classes = convert_str_to_json(y_pred_str, 'yPred')
    labels = sorted(set(y_true + y_pred_all_classes[0].keys()))
    n_instances = len(y_true)
    y_true_per_class = {class_: np.zeros(n_instances) for class_ in labels}
    for i, y in enumerate(y_true):
        y_true_per_class[y][i] = 1.0

    y_pred_per_class = {class_: np.zeros(n_instances) for class_ in labels}
    y_pred = []
    for i, y in enumerate(y_pred_all_classes):
        predicted_class = sorted(y.items(), key=lambda x: x[1], reverse=True)[0][0]
        y_pred_per_class[predicted_class][i] = y[predicted_class]
        y_pred.append(predicted_class)

    for threshold in np.arange(0.05, 1, 0.05):
        if any(binarize(y_pred_per_class[class_], threshold).sum() == 0 for class_ in labels):
            break
        if all(precision_score(y_true_per_class[class_],
                               binarize(y_pred_per_class[class_], threshold)) >= target_precision for class_ in
               labels) and \
                all(recall_score(y_true_per_class[class_],
                                 binarize(y_pred_per_class[class_], threshold)) >= target_recall for class_ in labels):
            entry = output_report(np.array(y_true), y_true_per_class, np.array(y_pred), y_pred_per_class, threshold)
            return entry

    return_error('Could not find threshold which satisfies the following conditions :\n\
    1. precision larger or equal than {} for all classes \n\
    2. recall larger or equal than {} for all classes'.format(target_precision, target_recall))


def convert_str_to_json(str_json, var_name):
    try:
        y_true = json.loads(str_json)
        return y_true
    except Exception as e:
        return_error('Exception while reading {} :{}'.format(var_name, e))


def main():
    y_pred_all_classes = demisto.args()["yPred"]
    y_true = demisto.args()["y_true"]
    target_precision = calculate_and_validate_float_parameter("targetPrecision")
    target_recall = calculate_and_validate_float_parameter("targetRecall")
    entry = find_threshold(y_pred_all_classes, y_true, target_precision, target_recall)
    demisto.results(entry)


def calculate_and_validate_float_parameter(var_name):
    try:
        res = float(demisto.args()[var_name]) if var_name not in demisto.args() else 0
    except Exception:
        return_error('{} must be a float between 0-1 or left empty'.format(var_name))
    if res < 0 or res > 1:
        return_error('{} must be a float between 0-1 or left empty'.format(var_name))
    return res


if __name__ in ['__main__', '__builtin__', 'builtins']:
    main()
