# Knowledge Explaining Distillation (KED)

This code repository implements KED in Python 3.8.

### KED with MLPs

- Unicauca.ipynb - Jupyter notebook implementing Unicauca dataset.

- MNIST.ipynb - Jupyter notebook implementing KED for MNIST dataset. 

- notMNIST.ipynb - Jupyter notebook implementing KED for FashionMNIST dataset.

- MNIST+notMNIST.ipynb - Jupyter notebook implementing KED for MNIST+FashionMNIST dataset.


### KED with CNNs

The 'teachers' folder contains total 15 teacher models for CIFAR10, CIFAR100, and Tiny Imagenet datasets. 

- kd - Contains .py files for implementing KD and KED methods.
- fitnet - Contains .py files for implementing FitNet augmented with KD and KED methods.
- at - Contains .py files for implementing attention transfer augmented with KD and KED methods.
- sp - Contains .py files for implementing similarity preservation augmented with KD and KED methods.

Each folder contains separate files for experiments with standard Resnets, wide Resnets and VGGs.
