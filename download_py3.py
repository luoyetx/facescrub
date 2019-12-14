#!/usr/bin/env python2.7
# coding: utf-8
import os
from os.path import join, exists
import multiprocessing
import hashlib
import cv2


files = ['facescrub_actors.txt', 'facescrub_actresses.txt']
RESULT_ROOT = './download'
if not exists(RESULT_ROOT):
    os.mkdir(RESULT_ROOT)


def download(*args): #(names, urls, bboxes)
    """
        download from urls into folder names using wget
    """

    assert(len(names) == len(urls))
    assert(len(names) == len(bboxes))

    # download using external wget
    CMD = 'wget -c -t 1 -T 3 "%s" -O "%s"'
    for i in range(len(names)):
        directory = join(RESULT_ROOT, names[i])
        if not exists(directory):
            os.mkdir(directory)
        fname = hashlib.sha1(urls[i].encode("utf-8")).hexdigest() + '.jpg'
        dst = join(directory, fname)
        print( "downloading", dst)
        if exists(dst):
            print( "already downloaded, skipping...")
            continue
        else:
            res = os.system(CMD % (urls[i], dst))
        # get face
        face_directory = join(directory, 'face')
        if not exists(face_directory):
            os.mkdir(face_directory)
        img = cv2.imread(dst)
        if img is None:
            # no image data
            os.remove(dst)
        else:
            face_path = join(face_directory, fname)
            face = img[bboxes[i][1]:bboxes[i][3], bboxes[i][0]:bboxes[i][2]]
            cv2.imwrite(face_path, face)
            # write bbox to file
            with open(join(directory,'_bboxes.txt'), 'a') as fd:
                bbox_str = ','.join([str(_) for _ in bboxes[i]])
                fd.write('%s %s\n' % (fname, bbox_str))


if __name__ == '__main__':
    for f in files:
        with open(f, 'r') as fd:
            # strip first line
            fd.readline()
            names = []
            urls = []
            bboxes = []
            for line in fd.readlines():
                components = line.split('\t')
                assert(len(components) == 6)
                name = components[0].replace(' ', '_')
                url = components[3]
                bbox = [int(_) for _ in components[4].split(',')]
                names.append(name)
                urls.append(url)
                bboxes.append(bbox)
        # every name gets a task
        last_name = names[0]
        task_names = []
        task_urls = []
        task_bboxes = []
        tasks = []
        for i in range(len(names)):
            if names[i] == last_name:
                task_names.append(names[i])
                task_urls.append(urls[i])
                task_bboxes.append(bboxes[i])
            else:
                tasks.append((task_names, task_urls, task_bboxes))
                task_names = [names[i]]
                task_urls = [urls[i]]
                task_bboxes = [bboxes[i]]
                last_name = names[i]
        tasks.append((task_names, task_urls, task_bboxes))

        pool_size = multiprocessing.cpu_count()
        pool = multiprocessing.Pool(processes=pool_size, maxtasksperchild=2)
        pool.map(download,tasks)
        pool.close()
        pool.join()
