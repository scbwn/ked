import numpy as np
import tensorflow as tf
import random as rn
np.random.seed(1)
rn.seed(2)
tf.random.set_seed(3)
import os
os.chdir("./env/KED/main/")

import sys
print(sys.argv[0])


from sklearn.preprocessing import StandardScaler, OneHotEncoder, LabelEncoder
from sklearn.utils import resample
from sklearn.metrics import confusion_matrix, balanced_accuracy_score, accuracy_score
from tensorflow.keras import backend as K
from tensorflow.keras.models import Model, Sequential
from tensorflow.keras.losses import categorical_crossentropy
from tensorflow.keras.layers import Layer, Input, Dense, Dropout, BatchNormalization, Activation, Add, Multiply, Lambda
from tensorflow.keras.layers import Conv2D, MaxPooling2D, Flatten, UpSampling2D, GlobalAveragePooling2D
from tensorflow.keras import regularizers
from tensorflow.keras.layers import Normalization, Resizing, RandomCrop, RandomFlip
from tensorflow.keras.activations import softmax
from tensorflow.keras.optimizers import SGD, RMSprop, Adagrad, Adadelta, Adam, Adamax, Nadam
from copy import deepcopy
import time


t_epoch=150
t_batch=100
d=(32,32,3)

# Superfeatures
M=4
num_of_classes=10


## Verbose
train_verbose = 1

###############################################################################
# FUNCTION DEFINITION
###############################################################################
def set_seed_TF2(seed):
    tf.random.set_seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)
    np.random.seed(seed)
    rn.seed(seed)
    
def random_crop(img, random_crop_size):
    # Note: image_data_format is 'channel_last'
    # SOURCE: https://jkjung-avt.github.io/keras-image-cropping/
    assert img.shape[2] == 3
    height, width = img.shape[0], img.shape[1]
    dy, dx = random_crop_size
    x = np.random.randint(0, width - dx + 1)
    y = np.random.randint(0, height - dy + 1)
    return img[y:(y+dy), x:(x+dx), :]


def crop_generator(batches, crop_length):
    """Take as input a Keras ImageGen (Iterator) and generate random
    crops from the image batches generated by the original iterator.
    SOURCE: https://jkjung-avt.github.io/keras-image-cropping/
    """
    while True:
        batch_x, batch_y = next(batches)
        batch_crops = np.zeros((batch_x.shape[0], crop_length, crop_length, 3))
        for i in range(batch_x.shape[0]):
            batch_crops[i] = random_crop(batch_x[i], (crop_length, crop_length))
        yield (batch_crops, batch_y)
    
def resnet_layer(x,
                 num_filters,
                 kernel_size=3,
                 strides=1,
                 activation='relu',
                 batch_normalization=True):

    conv = Conv2D(num_filters,
                  kernel_size=kernel_size,
                  strides=strides,
                  padding='same',
                  kernel_initializer='he_normal',
                  kernel_regularizer=regularizers.l2(5E-4))
    x = conv(x)
    if batch_normalization:
        x = BatchNormalization()(x)
    if activation is not None:
        x = Activation(activation)(x)
    return x

def shared_layers(x, filters=16*2, depth=44):
    if (depth - 2) % 6 != 0:
        raise ValueError('depth should be 6n+2 (eg 20, 32, 44 in [a])')
    num_filters = filters
    num_res_blocks = int((depth - 2) / 6)

    x = resnet_layer(x, num_filters=num_filters)
    for stack in range(2):
        for res_block in range(num_res_blocks):
            strides = 1
            if stack > 0 and res_block == 0:
                strides = 2  # downsample
            y = resnet_layer(x,
                             num_filters=num_filters,
                             strides=strides)
            y = resnet_layer(y,
                             num_filters=num_filters,
                             activation=None)
            if stack > 0 and res_block == 0:  # first layer but not first stack
                pad_dim=num_filters-x.shape[-1]
                paddings=tf.constant([[0, 0,], [0, 0], [0, 0], [pad_dim-pad_dim//2, pad_dim//2]])
                x = tf.pad(x[:, ::2, ::2, :], paddings, mode="CONSTANT")
            x = Add()([x, y])
            x = Activation('relu')(x)
        num_filters*=2
    return x
    
def branch_layers(x, filters=64*2, depth=44):
    if (depth - 2) % 6 != 0:
        raise ValueError('depth should be 6n+2 (eg 20, 32, 44 in [a])')
    num_filters = filters
    num_res_blocks = int((depth - 2) / 6)
    
    for stack in range(2,3):
        for res_block in range(num_res_blocks):
            strides = 1
            if stack > 0 and res_block == 0:
                strides = 2  # downsample
            y = resnet_layer(x,
                             num_filters=num_filters,
                             strides=strides)
            y = resnet_layer(y,
                             num_filters=num_filters,
                             activation=None)
            if stack > 0 and res_block == 0:  # first layer but not first stack
                pad_dim=num_filters-x.shape[-1]
                paddings=tf.constant([[0, 0,], [0, 0], [0, 0], [pad_dim-pad_dim//2, pad_dim//2]])
                x = tf.pad(x[:, ::2, ::2, :], paddings, mode="CONSTANT")
            x = Add()([x, y])
            x = Activation('relu')(x)
        num_filters*=2
    x = GlobalAveragePooling2D()(x)
    return x

def model_nn_teacher(d, num_of_classes):
    set_seed_TF2(100)
    inp=Input(shape=d)
    shared_op = shared_layers(inp)
    shared_op = Layer(name='shared_op')(shared_op)
    flat_inp=branch_layers(shared_op)
    op=Dense(num_of_classes, activation='softmax')(flat_inp)
    nn = Model(inputs=inp, outputs=op)
    nn.compile(optimizer=SGD(momentum=0.9, nesterov=True), loss='categorical_crossentropy', metrics=['accuracy'])
    return nn

def model_exp_teacher(d, num_of_classes):
    set_seed_TF2(100)
    inp=Input(shape=d)
    shared_op = shared_layers(inp)
    shared_op = resnet_layer(shared_op, num_filters=M*62, kernel_size=1)
    shared_op = Layer(name='shared_op')(shared_op)
    shared_op_list=tf.split(shared_op, M, axis=-1)
    logits=[]
    for i in range(M):
        flat_inp=branch_layers(shared_op_list[i], filters=62)
        y=Dense(num_of_classes, activation='softmax', name='sf_'+str(i+1))(flat_inp)
        logits.append(tf.math.log(y+1E-15))
    tot_logit=Add()(logits)
    op=Activation('softmax')(tot_logit)
    nn = Model(inputs=inp, outputs=op)
    nn.compile(optimizer=SGD(momentum=0.9, nesterov=True), loss='categorical_crossentropy', metrics=['accuracy'])
    return nn

def lr_scheduler(epoch):
    lr=0.01
    if epoch>=10:
        lr=0.05
    if epoch>=120:
        lr=0.005
    if epoch>=140:
        lr=0.0005
    return lr

def solve(a, b, c):
    if(b*b-4*a*c)<0:
        raise ValueError('Problem is not feasible.')
    sol=np.max(np.roots([a,b,c]))
    return int(sol)

def confidence_interval(a,l):
    import numpy as np, scipy.stats as st
    return st.t.interval(l, len(a)-1, loc=np.mean(a), scale=st.sem(a))

def bootstrap_score(y_test, y_pred, metric=accuracy_score, l=0.95, seed=100):
    rng = np.random.RandomState(seed=seed)
    idx = np.arange(y_test.shape[0])
    test_accuracies = []
    for i in range(200):
        pred_idx = rng.choice(idx, size=idx.shape[0], replace=True)
        acc_test_boot = metric(y_test[pred_idx], y_pred[pred_idx])
        test_accuracies.append(acc_test_boot)
    bootstrap_score_mean = np.mean(test_accuracies)
    [ci_lower, ci_upper] = confidence_interval(test_accuracies,l)
    return bootstrap_score_mean, 0.5*(ci_upper-ci_lower)

###############################################################################
# EXPERIMENT
###############################################################################

# Dataset Preprocessing
from tensorflow.keras.datasets import cifar10
(x_train, y_train), (x_test, y_test)=cifar10.load_data()

x_train=x_train.astype(np.float32)/255
x_test=x_test.astype(np.float32)/255

# Scaling
mean=x_train.mean((0,1,2))
std=x_train.std((0,1,2))
paddings = tf.constant([[0, 0,], [4, 4], [4, 4], [0, 0]])
x_train = tf.pad(x_train, paddings, mode="CONSTANT")
x_train=(x_train-mean)/std
x_test=(x_test-mean)/std

y_train=y_train.reshape(-1,1)
y_test=y_test.reshape(-1,1)


# One-hot Encoding
enc = OneHotEncoder(sparse=False)
y_train=enc.fit_transform(y_train)


# Data generator for training data
from tensorflow.keras.preprocessing.image import ImageDataGenerator
train_generator = ImageDataGenerator(horizontal_flip = True)

# Generate training batches
train_batches = train_generator.flow(x_train, y_train, batch_size=t_batch)
train_batches = crop_generator(train_batches, d[0])

callbacks = [tf.keras.callbacks.LearningRateScheduler(lr_scheduler)]
###############################################################################
# TEACHER
###############################################################################
teacher=model_nn_teacher(d,num_of_classes)
teacher.fit(train_batches, steps_per_epoch=x_train.shape[0]//t_batch, epochs=t_epoch, callbacks=callbacks, verbose=train_verbose)
y_pred_test=teacher.predict(x_test)

from sklearn.metrics import confusion_matrix, accuracy_score
print('Priviledged Test Classification')
print(confusion_matrix(y_test, np.argmax(y_pred_test,1)))
print(bootstrap_score(y_test, np.argmax(y_pred_test,1)))
teacher.save('./models/cifar10-resnet44/teacher.h5')

###############################################################################
# EXPLAINING TEACHER
###############################################################################
new_teacher=model_exp_teacher(d,num_of_classes)
new_teacher.fit(train_batches, steps_per_epoch=x_train.shape[0]//t_batch, epochs=t_epoch, callbacks=callbacks, verbose=train_verbose)
y_pred_test=new_teacher.predict(x_test)

print('Explaining Teacher Test Classification')
print(confusion_matrix(y_test, np.argmax(y_pred_test,1)))
print(bootstrap_score(y_test, np.argmax(y_pred_test,1)))
new_teacher.save('./models/cifar10-resnet44/new_teacher.h5')