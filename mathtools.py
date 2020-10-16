import numpy as np
import matplotlib.pyplot as plt


def mean_downscaler(data, n):
    n = int(n)
    mod = len(data) % n
    if mod != 0:
        n += mod
    meanArr = []
    finalArr = []
    for i in data:
        meanArr.append(i)
        if len(meanArr) == n:
            finalArr.append(np.sum(meanArr))
            meanArr = []
        else:
            continue
    return finalArr
