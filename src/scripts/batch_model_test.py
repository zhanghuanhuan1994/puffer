#!/usr/bin/env python3 
# python csv_parser.py --file-path ~/Documents/puffer-201903/ --output-path ~/Documents/fork_puffer/training_data_foler --start-date 20190325 --end-date 20190330
import json
import argparse
import yaml
import datetime
import sys
import os
from datetime import datetime, timedelta
import numpy as np
from multiprocessing import Process, Array, Pool
import pandas as pd
import matplotlib
import subprocess
import gc
from csv_parser_n import(    
    read_csv_to_rows,
    process_raw_csv_data,
prepare_input_output)

from ttp_local3 import Model

# gs://puffer-data-release/2019-01-26T11_2019-01-27T11/video_sent_2019-01-26T11_2019-01-27T11.csv
FUTURE_CHUNKS = 5
model_path ="./model_dir/"

def model_test(pt_file, raw_in_data, raw_out_data, date_str=None):
    model = Model()
    model.load(pt_file)
    input_data = model.normalize_input(raw_in_data, update_obs=False)
    output_data = raw_out_data
    input_data = np.array(input_data)
    output_data = np.array(output_data)
    accuracy, _ = model.compute_accuracy(input_data, output_data)
    print("Model Test: ", date_str," ", pt_file, " ", str(accuracy))
    return accuracy

def parse_file(video_sent_file, video_acked_file):
    video_sent_rows =  read_csv_to_rows(None, video_sent_file)
    video_acked_rows = read_csv_to_rows(None, video_acked_file)
    print("read_and_write_csv_proc  ", len(video_sent_rows), " ", 
        len(video_acked_rows),  " complete reading rows, will process the raw csv ")
    raw_data = process_raw_csv_data(video_sent_rows, video_acked_rows, None)
    raw_in_out = prepare_input_output(raw_data)

    return raw_in_out
def model_test_on_one_day(date_item, models):
    pool = Pool(processes= FUTURE_CHUNKS*2)
    next_date_item = date_item+timedelta(days=1)
    # piece the file name
    date_str1 = str(date_item.year)+"-"+str(date_item.month).zfill(2)+"-"+str(date_item.day).zfill(2)+"T11"
    date_str2 = str(next_date_item.year)+"-"+str(next_date_item.month).zfill(2)+"-"+str(next_date_item.day).zfill(2)+"T11"
    date_str = date_str1+"_"+date_str2
    video_sent_file = "video_sent_"+date_str+".csv"
    video_acked_file = "video_acked_"+date_str+".csv"
    gs_video_sent_file_path = "gs://puffer-data-release/"+date_str+"/"+video_sent_file
    gs_video_acked_file_path =  "gs://puffer-data-release/"+date_str+"/"+video_acked_file
    cmd = "gsutil cp "+gs_video_sent_file_path+" ./"
    subprocess.call(cmd, shell=True)
    cmd = "gsutil cp "+gs_video_acked_file_path+" ./"
    subprocess.call(cmd, shell=True)
    raw_in_out = parse_file(video_sent_file, video_acked_file)
    if len(raw_in_out[0]['in'])== 0 or  len(raw_in_out[0]['out'])== 0:
        cmd = "rm -f "+ video_sent_file+" "+video_acked_file
        subprocess.call(cmd, shell=True)
        pool.close()
        pool.join()
        return 1
    else:
        for j in range(FUTURE_CHUNKS):
            print(j," ",len(raw_in_out[j]['in']), " ", len(raw_in_out[j]['out']))

    result_proc = {}
    results = {}
    for j in range(FUTURE_CHUNKS):
        for pt_file in models[j]: 
            result_proc[pt_file] = (pool.apply_async(model_test, args=(model_path+pt_file, raw_in_out[j]['in'], raw_in_out[j]['out'],date_str1, ) ))
    for key in result_proc:
        accuracy = result_proc[key].get()
        results[key] = accuracy 
    result_file_name = date_str+"-result"
    with open(result_file_name, "w") as f:
        f.write(json.dumps(results))
    cmd = "rm -f "+ video_sent_file+" "+video_acked_file
    subprocess.call(cmd, shell=True)
    pool.close()
    pool.join()

def model_test_on_one_day_no_pool(date_item, models):
    next_date_item = date_item+timedelta(days=1)
    # piece the file name
    date_str1 = str(date_item.year)+"-"+str(date_item.month).zfill(2)+"-"+str(date_item.day).zfill(2)+"T11"
    date_str2 = str(next_date_item.year)+"-"+str(next_date_item.month).zfill(2)+"-"+str(next_date_item.day).zfill(2)+"T11"
    date_str = date_str1+"_"+date_str2
    video_sent_file = "video_sent_"+date_str+".csv"
    video_acked_file = "video_acked_"+date_str+".csv"
    gs_video_sent_file_path = "gs://puffer-data-release/"+date_str+"/"+video_sent_file
    gs_video_acked_file_path =  "gs://puffer-data-release/"+date_str+"/"+video_acked_file
    cmd = "gsutil cp "+gs_video_sent_file_path+" ./"
    subprocess.call(cmd, shell=True)
    cmd = "gsutil cp "+gs_video_acked_file_path+" ./"
    subprocess.call(cmd, shell=True)
    raw_in_out = parse_file(video_sent_file, video_acked_file)
    if len(raw_in_out[0]['in'])== 0 or  len(raw_in_out[0]['out'])== 0:
        cmd = "rm -f "+ video_sent_file+" "+video_acked_file
        subprocess.call(cmd, shell=True)
        return 1
        
    results = {}
    for j in range(FUTURE_CHUNKS):
        for pt_file in models[j]: 
            results[pt_file] = model_test(model_path+pt_file, raw_in_out[j]['in'], raw_in_out[j]['out'], date_str1,)
    result_file_name = date_str+"-result"
    with open(result_file_name, "w") as f:
        f.write(json.dumps(results))
    cmd = "rm -f "+ video_sent_file+" "+video_acked_file
    subprocess.call(cmd, shell=True)
    return 1


def main():
    parser = argparse.ArgumentParser()                     
    parser.add_argument('--start-date', dest='start_date',
                        help='The start date of the model training')  
    parser.add_argument('--end-date', dest='end_date',
                        help='The end_date date of the model training')  
    args = parser.parse_args()
    models = [[] for i in range(FUTURE_CHUNKS) ]
    dir1 = os.listdir(model_path)
    for file_name in dir1:
        pt_index = int(file_name[-4])
        models[pt_index].append(file_name)

    #print(models)

    start_dt = datetime.strptime(args.start_date,"%Y%m%d")
    end_dt = datetime.strptime(args.end_date,"%Y%m%d")
    day_num = (end_dt - start_dt).days+1

    # for i in range(day_num):
    #     date_item = start_dt + timedelta(days=i)
    #     print(date_item, " Start")
    #     # print("pt file ", pt_file)
    #     model_test_on_one_day(date_item, models)
    #     print(date_item, " FIN")

    pool = Pool(processes= 4)
    result_procs = []
    for i in range(day_num):
        date_item = start_dt + timedelta(days=i)
        print(date_item, " Start")
        result_procs.append(pool.apply_async(model_test_on_one_day_no_pool, args=(date_item, models,)))
    for result in result_procs:
        result.get()
    pool.close()
    pool.join()







if __name__ == '__main__':
    main()
