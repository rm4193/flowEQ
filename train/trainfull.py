from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import io
import sys
from datetime import datetime
from packaging import version

import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow.keras import layers
import matplotlib.pyplot as plt

from models import *
from utils import *

print("TensorFlow version: ", tf.__version__)
assert version.parse(tf.__version__).release[0] >= 2, \
    "This script requires TensorFlow 2.0 or above."

# load normalized data from file
eq_params = pd.read_csv("../data/safe/normalized_eq_params.csv", sep=",", index_col=0)
count = pd.read_csv("../data/safe/descriptors.csv", sep=",", index_col=0)

# only use data points within the top 2 occuring descriptors
top_descriptors = count.loc[0:1, 'descriptor'].tolist()
eq_df = eq_params[eq_params['descriptor'].isin(top_descriptors)]

# make train / test split
train_set = 1000
x_train = eq_df.values[:train_set,1:]
y_train = eq_df.values[:train_set,1]
x_test  = eq_df.values[train_set:,1:]
y_test  = eq_df.values[train_set:,1]

# inspect training and testing data
print("Training set   : ", x_train.shape)
print("Traing labels  : ", y_train.shape)
print("Testing set    : ", x_test.shape)
print("Testing labels : ", y_test.shape)

# create directories for models
model_dir = os.path.join('../models', datetime.now().strftime("%Y%m%d-%H%M%S"))
if not os.path.isdir(model_dir):
    os.makedirs(model_dir)
    os.makedirs(os.path.join(model_dir, "autoencoders"))
    os.makedirs(os.path.join(model_dir, "decoders"))
    os.makedirs(os.path.join(model_dir, "encoders"))
    os.makedirs(os.path.join(model_dir, "plots"))

latent_dims = [1, 2, 3]
beta_vals   = [0.000, 0.001, 0.010, 0.020]
epochs      = 300

for latent_dim in latent_dims:
    for beta_max in beta_vals:

        # KL annealing (β) setup
        beta = K.variable(0.0)
        klstart = 50
        annealtime = 5000

        class kl_annealing_callback(tf.keras.callbacks.Callback):
            def __init__(self, beta):
                self.beta = beta

            def on_epoch_end(self, epoch, logs={}):
                if epoch > klstart:
                    new_beta = min(K.get_value(self.beta) + (1./ annealtime), beta_max)
                    K.set_value(self.beta, new_beta)
                print ("Current KL Weight is " + str(K.get_value(self.beta)))

        # construct the model
        autoencoder, encoder, decoder = build_single_layer_variational_autoencoder(latent_dim, x_train.shape[1], beta)

        # train the model
        autoencoder.fit(x_train, x_train, 
                        shuffle=True,
                        validation_data=(x_test,x_test),
                        batch_size=8, 
                        epochs=epochs,
                        callbacks=[kl_annealing_callback(beta)],
                        verbose=True)

        # save the model weights
        autoencoder.save_weights(os.path.join(model_dir,"autoencoders",f"vae{latent_dim}d_beta_{beta_max:0.4f}.h5"), save_format='h5')
        encoder.save_weights(os.path.join(model_dir,"encoders",f"encoder{latent_dim}d_beta_{beta_max:0.4f}.h5"), save_format='h5')
        decoder.save_weights(os.path.join(model_dir,"decoders",f"decoder{latent_dim}d_beta_{beta_max:0.4f}.h5"), save_format='h5')

        # Save the model architectures
        with open(os.path.join(model_dir,"autoencoders",f"vae{latent_dim}d_beta_{beta_max:0.4f}.json"), 'w') as f:
            f.write(autoencoder.to_json())
        with open(os.path.join(model_dir,"encoders",f"encoder{latent_dim}d_beta_{beta_max:0.4f}.json"), 'w') as f:
            f.write(encoder.to_json())
        with open(os.path.join(model_dir,"decoders",f"decoder{latent_dim}d_beta_{beta_max:0.4f}.json"), 'w') as f:
            f.write(decoder.to_json())

        # save out plots of final results
        classes = {b: a for a, b in enumerate(set(top_descriptors))}
        labels = eq_df['descriptor'][:train_set].map(classes, na_action='ignore').values
        models = (encoder, decoder)
        data = (x_train, labels, classes)
        plot_manifold(models, dim=latent_dim, data=data, size=15, variational=True,
                to_file=os.path.join(model_dir,"plots",f"{latent_dim}d_beta{beta_max}_manifold_{epochs}_"))

        # reset session for training of next model
        K.clear_session()