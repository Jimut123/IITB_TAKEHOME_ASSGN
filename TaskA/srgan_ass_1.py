#!/usr/bin/env python3
# encoding: utf-8
# @Time    : 05/05/2022 15:56
# @Author  : Jimut Bahan Pal
# Some part of the code is stolen from here: https://www.kaggle.com/code/akhileshdkapse/sr-super-resolution-gan-keras/notebook

import os
import time
import random
import glob
import numpy as np

from tqdm import tqdm
import cv2
from PIL import Image
import matplotlib.pyplot as plt

###====================== HYPER-PARAMETERS ===========================###
## Adam
batch_size = 16
lr_v = 1e-5

# change the stuff here
tot_sample= 10000  # Total traning images


## adversarial learning (SRGAN)
n_epoch = 10000
## initialize G
n_epoch_init = n_epoch//10

# create folders to save result images and trained models
save_dir = "samples"
checkpoint_dir = "models"
#track image as per index
# save_ind= 16

save_ind = [i for i in range(30)]

if not os.path.exists(save_dir):
    os.makedirs(save_dir)
if not os.path.exists(checkpoint_dir):
    os.makedirs(checkpoint_dir)


def load(path,shape):
    img= cv2.imread(path)
    img= cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img= cv2.resize(img, shape)
    return img


def get_data(path):
    X=[]
    Y=[]
    # google colab is weak, use 5000 images
    all_images = glob.glob('{}/*'.format(path))
    for img_path in tqdm(all_images):
        X.append(load(img_path,(256,256)))
        # 4 times smaller
        Y.append(load(img_path,(64,64)))


    X= np.array(X)
    Y= np.array(Y)
    return X/255.0, Y/255.0


HR_train, LR_train = get_data('Kolkata_020/train')
print(HR_train.shape, LR_train.shape)

HR_test, LR_test = get_data('Kolkata_020/test')
print(HR_test.shape, LR_test.shape)


print("Length = ************************************************** ",len(save_ind))
for item_arr in range(len(save_ind)):
    f, ax= plt.subplots(1,2, figsize=(14, 6))
    ax[0].imshow(LR_test[item_arr], aspect='auto')
    ax[1].imshow(HR_test[item_arr], aspect='auto')
    plt.savefig('high_low/low_res_high_res_{}.png'.format(item_arr))




# Model 

import tensorflow as tf
from tensorflow.keras.layers import Input, Conv2D, Flatten, Dense, add,\
                                    BatchNormalization, Activation, LeakyReLU, Layer

from tensorflow.keras.models import Model

class SubpixelConv2D(Layer):
    """ Subpixel Conv2D Layer
    upsampling a layer from (h, w, c) to (h*r, w*r, c/(r*r)),
    where r is the scaling factor, default to 4
    # Arguments
    upsampling_factor: the scaling factor
    # Input shape
        Arbitrary. Use the keyword argument `input_shape`
        (tuple of integers, does not include the samples axis)
        when using this layer as the first layer in a model.
    # Output shape
        the second and the third dimension increased by a factor of
        `upsampling_factor`; the last layer decreased by a factor of
        `upsampling_factor^2`.
    # References
        Real-Time Single Image and Video Super-Resolution Using an Efficient
        Sub-Pixel Convolutional Neural Network Shi et Al. https://arxiv.org/abs/1609.05158
    """

    def __init__(self, upsampling_factor=2, **kwargs):
        super(SubpixelConv2D, self).__init__(**kwargs)
        self.upsampling_factor = upsampling_factor

    def build(self, input_shape):
        last_dim = input_shape[-1]
        factor = self.upsampling_factor * self.upsampling_factor
        if last_dim % (factor) != 0:
            raise ValueError('Channel ' + str(last_dim) + ' should be of '
                             'integer times of upsampling_factor^2: ' +
                             str(factor) + '.')

    def call(self, inputs, **kwargs):
        return tf.nn.depth_to_space( inputs, self.upsampling_factor )

    def get_config(self):
        config = { 'upsampling_factor': self.upsampling_factor, }
        base_config = super(SubpixelConv2D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))

    def compute_output_shape(self, input_shape):
        factor = self.upsampling_factor * self.upsampling_factor
        input_shape_1 = None
        if input_shape[1] is not None:
            input_shape_1 = input_shape[1] * self.upsampling_factor
        input_shape_2 = None
        if input_shape[2] is not None:
            input_shape_2 = input_shape[2] * self.upsampling_factor
        dims = [ input_shape[0],
                 input_shape_1,
                 input_shape_2,
                 int(input_shape[3]/factor)
               ]
        return tuple( dims )


#Generator
def get_G(input_shape):
    # w_init = tf.random_normal_initializer(stddev=0.02)
    g_init = tf.random_normal_initializer(1., 0.02)
    relu= Activation('relu')

    nin= Input(shape= input_shape)
    n= Conv2D(64, (3,3), padding='SAME', activation= 'relu',
                        kernel_initializer='HeNormal')(nin)
    temp= n


    # B residual blocks
    for i in range(3):
        nn= Conv2D(64, (3,3), padding='SAME', kernel_initializer='HeNormal')(n)
        nn= BatchNormalization(gamma_initializer= g_init)(nn)
        nn= relu(nn)
        nn= Conv2D(64, (3,3), padding='SAME', kernel_initializer='HeNormal')(n)
        nn= BatchNormalization(gamma_initializer= g_init)(nn)

        nn= add([n, nn])
        n= nn

    n= Conv2D(64, (3,3), padding='SAME', kernel_initializer='HeNormal')(n)
    n= BatchNormalization(gamma_initializer= g_init)(n)
    n= add([n, temp])
    # B residual blacks end

    n= Conv2D(256, (3,3), padding='SAME', kernel_initializer='HeNormal')(n)
    n= SubpixelConv2D(upsampling_factor=2)(n)
    n= relu(n)

    n= Conv2D(256, (3,3), padding='SAME', kernel_initializer='HeNormal')(n)
    n= SubpixelConv2D(upsampling_factor=2)(n)
    n= relu(n)

    nn= Conv2D(3, (1,1), padding='SAME', kernel_initializer='HeNormal', activation= 'tanh')(n)


    G = Model(inputs=nin, outputs=nn, name="generator")
    return G


# discriminator
def get_D(input_shape):

    g_init= tf.random_normal_initializer(1., 0.02)
    ly_relu= LeakyReLU(alpha= 0.2)
    df_dim = 16

    nin = Input(input_shape)
    n = Conv2D(64, (4, 4), (2, 2), padding='SAME', kernel_initializer='HeNormal')(nin)
    n= ly_relu(n)

    for i in range(2, 6):
        n = Conv2D(df_dim*(2**i),(4, 4), (2, 2), padding='SAME', kernel_initializer='HeNormal')(n)
        n= ly_relu(n)
        n= BatchNormalization(gamma_initializer= g_init)(n)

    n= Conv2D(df_dim*16, (1, 1), (1, 1), padding='SAME', kernel_initializer='HeNormal')(n)
    n= ly_relu(n)
    n= BatchNormalization(gamma_initializer= g_init)(n)

    n= Conv2D(df_dim*8, (1, 1), (1, 1), padding='SAME', kernel_initializer='HeNormal')(n)
    n= BatchNormalization(gamma_initializer= g_init)(n)
    temp= n

    n= Conv2D(df_dim*4, (3, 3), (1, 1), padding='SAME', kernel_initializer='HeNormal')(n)
    n= ly_relu(n)
    n= BatchNormalization(gamma_initializer= g_init)(n)

    n= Conv2D(df_dim*8, (3, 3), (1, 1), padding='SAME', kernel_initializer='HeNormal')(n)
    n= BatchNormalization(gamma_initializer= g_init)(n)

    n= add([n, temp])

    n= Flatten()(n)
    no= Dense(units=1, kernel_initializer='HeNormal', activation= 'sigmoid')(n)
    D= Model(inputs=nin, outputs=no, name="discriminator")

    return D


# VGG19
def get_vgg19():
    vgg= tf.keras.applications.VGG19( include_top=False, weights='imagenet', 
                                    input_tensor=None, input_shape=(256, 256, 3),
                                    pooling=None, classes=1000, classifier_activation='softmax' )

    inp= Input(shape=(256, 256, 3))
    x= vgg.layers[0](inp)
    for ly in vgg.layers[1:17]:
        x= ly(x)
    VGG19= Model(inp, x)

    return VGG19



G = get_G((64, 64, 3))
D = get_D((256, 256, 3))
vgg= get_vgg19()



# Optimizers
g_optimizer_init = tf.optimizers.Adam(lr_v)
g_optimizer = tf.optimizers.Adam(lr_v)
d_optimizer = tf.optimizers.Adam(lr_v)


n_step_epoch = round(n_epoch_init // batch_size)
for epoch in range(n_epoch_init):
  i,j= ((epoch)*batch_size)%tot_sample, (((epoch+1))*batch_size)%tot_sample
  if j== 0:
    j= -1
  X, Y= LR_train[i: j], HR_train[i: j]
  with tf.GradientTape() as tape:
      ypred= G(X)
      mse_loss= tf.reduce_mean(tf.reduce_mean(tf.math.squared_difference(Y, ypred), axis=-1))
      grad = tape.gradient(mse_loss, G.trainable_weights)
      g_optimizer_init.apply_gradients(zip(grad, G.trainable_weights))
        
  print("Epoch: [{}/{}] step: mse: {:.3f} ".format(
            epoch, n_epoch_init , mse_loss))
  text_app = "{} {} {} \n".format(epoch, n_epoch_init, mse_loss)
  with open("first.txt", "a") as myfile:
    myfile.write(text_app)
  if epoch%500 ==0:  ############################################## change it to 100
    for item_arr in range(len(save_ind)):
      img= G.predict(LR_test[np.newaxis, item_arr])[0]
      #img= (img-img.mean())/img.std()
      img= Image.fromarray(np.uint8(img*255))
      img.save(os.path.join('changes/', '{}/init_g_{}.png'.format(item_arr,epoch)))


f, ax= plt.subplots(1,5, figsize=(16, 6))
for i, file in enumerate(glob.glob('./samples/init*')):
    img= load(file, shape=(256, 256))
    ax[i].imshow(img)
# plt.show()
plt.savefig('initial_changes.png'.format(i))



 ########################################3 change it to another value

for epoch in range(n_epoch):
        i,j= ((epoch)*batch_size)%tot_sample, (((epoch+1))*batch_size)%tot_sample
        if j== 0:
            j= -1
        X, Y= LR_train[i: j], HR_train[i: j]
        with tf.GradientTape(persistent=True) as tape:
            fake_img= G(X)
            fake_logits= D(fake_img)
            real_logits= D(Y)
            fake_feature= vgg(fake_img)
            real_feature= vgg(Y)

            #D. loss
            d_loss1= tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(fake_logits , tf.zeros_like(fake_logits)))
            d_loss2= tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(real_logits,tf.ones_like(real_logits)))
            d_loss= d_loss1 + d_loss2

            #G. loss
            g_gan_loss= 2e-3*tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(fake_logits , tf.ones_like(fake_logits)))
            mse_loss=  2e-1* tf.reduce_mean(tf.reduce_mean(tf.math.squared_difference(fake_img, Y), axis=-1))
            vgg_loss = 2e-6 * tf.reduce_mean(tf.reduce_mean(tf.math.squared_difference(fake_feature, real_feature), axis=-1))
            g_loss = mse_loss + vgg_loss + g_gan_loss

            grad = tape.gradient(g_loss, G.trainable_weights)
            g_optimizer.apply_gradients(zip(grad, G.trainable_weights))
            grad = tape.gradient(d_loss, D.trainable_weights)
            d_optimizer.apply_gradients(zip(grad, D.trainable_weights))

        print("Epoch: [{}/{}] step: D.loss: {:.3f}: G.loss: {:.3f}".format(
                epoch, n_epoch , d_loss, g_loss))
        text_app = "{} {} {} {} \n".format(epoch, n_epoch, d_loss, g_loss)
        with open("second.txt", "a") as myfile:
            myfile.write(text_app)


        if epoch%500 ==0: ###################################################3 change it to 100
            for item_arr in range(len(save_ind)):
                img= G.predict(LR_test[np.newaxis, item_arr])[0]
                # if not sigmoid
                #img= (img-img.mean())/img.std()
                img= Image.fromarray(np.uint8(img*255))
                img.save(os.path.join('changes/', '{}/train_g_{}.png'.format(item_arr,epoch)))


# f, ax= plt.subplots(3,5, figsize=(14, 16))
# for i, file in enumerate(glob.glob('./samples/train*')[:15]):
#     img= load(file, shape=(256, 256))
#     ax[i//5][i%5].imshow(img, aspect='auto')

# plt.savefig('changes_over_time.png'.format(i))

for item_arr in range(len(save_ind)):
    f, ax= plt.subplots(1,3, figsize=(16, 6))
    ax[0].imshow(LR_test[item_arr], aspect='auto')
    ax[1].imshow(load(glob.glob('./changes/{}/train*'.format(item_arr))[-1], (256, 256)), aspect='auto')
    ax[2].imshow(HR_test[item_arr], aspect='auto')
    # plt.show()
    plt.savefig('save_results/save_result_full_{}.png'.format(item_arr))
