#!/usr/bin/python3

import sys
sys.path.append('/home/david/bin')
sys.path.append('/home/david/dev/common')
from readprocpar import procparReader
from readfdf import fdfReader

from writenifti import niftiWriter
import matplotlib.pyplot as plt
import numpy as np
import scipy.optimize as opt
import glob
import math
import time

def load_data():
	# returns list of data

	def ifft(inkdata):

		inkdata = np.fft.fftshift(inkdata,axes=(2,3))
		ifft_data = np.fft.ifft2(inkdata,axes=(2,3), norm='ortho')
		ifft_data = np.fft.ifftshift(ifft_data,axes=(2,3))
		return ifft_data

	folder = '/home/david/dev/dixon/s_2018080901'
	name_list =  glob.glob(folder+'/fsems2*img')
	ind = [0,3,6]
	rawre = sorted([i for i in name_list if 'rawRE' in i ])
	rawim = sorted([i for i in name_list if 'rawIM' in i ])
	#print('\n'.join(rawim))
	#getting only the -pi, 0, pi
	combined_names = [[rawre[i],rawim[i]] for i in ind]
	data = []
	roshift = []
	for item in combined_names:
		ppr = procparReader(item[0]+'/procpar')
		roshift.append(float(ppr.read()['roshift']))
		hdr , data_re = fdfReader(item[0],'out').read()
		hdr , data_im = fdfReader(item[1],'out').read()
		cdata = np.vectorize(complex)(data_re[0,...],data_im[0,...])
		data.append(ifft(cdata))
	print(data[0].shape)
	print(roshift)

	return data, roshift

class dixon():

	def __init__(self, data, roshift, freq, fieldmap=None):
		self.data = np.asarray(data)
		self.roshift = roshift
		self.freq = freq
		print('self.data.shape : '+str(self.data.shape))
	
	def ideal(self):
		"""
		F,S,RO : k th iter
		Fp,Sp,ROp : k+1 th iter 
		"""
		def make_Acd(roshift,freq=[0,1400]):
			A = np.zeros((2*len(roshift),2*len(freq)))
			#print(A.shape)
			print('roshift: '+str(roshift))
			print('freqs : '+str(freq))
			#c = np.zeros(len(freq),len(roshift))
			#d = np.zeros(len(freq),len(roshift))
			c = np.asarray([math.cos(2*np.pi*i*j) for i in freq for j in roshift])
			d = np.asarray([math.sin(2*np.pi*i*j) for i in freq for j in roshift])
			c = np.reshape(c,(len(freq),len(roshift)),order='c')
			d = np.reshape(d,(len(freq),len(roshift)),order='c')
			
			A[:len(roshift),0::2] = c.T
			A[len(roshift):,0::2] = d.T
			A[:len(roshift),1::2] = -d.T
			A[len(roshift):,1::2] = c.T 
			#print(c)
			#print(d)
			print(A)
			return A, c, d

		def fit(data1D, roshift,A,c,d,F0=0, freq=[0,1400]):
			"""
			1d function to be used for apply_along_axis
			F0 is initial field
			freq is the Dixon components frequency shift
			"""
			def Sh_from_f(data1D, field, freq, roshift):

				#print('data1D : '+str(data1D))
				# making Shat from raw S
				Sh = data1D*np.exp(-1j*2*np.pi*field*np.asarray(roshift))
				#print('sh shape at shfromf : '+str(Sh.shape))
				# making real vector from intensities by separating real and imaginary
				Sre = np.asarray([np.real(Sh[i]) for i in range(Sh.shape[0])])
				Sim = np.asarray([np.imag(Sh[i]) for i in range(Sh.shape[0])])
				# making the A matrix
				#A = makeA(freq,roshift)
				#b = np.concatenate((Sre,Sim),axis=0)
				return np.concatenate((Sre, Sim),axis=0).T # return col vector

			
			def ro_from_Sh(S,A):

				return np.linalg.multi_dot((np.linalg.inv(np.dot(A.T,A)),A.T,S))

			def B_from_ro(ro,A,c,d,roshift,freq):

				B = np.zeros((A.shape[0],A.shape[1]+1))
				B[:,1:] = A
				rore = ro[0::2]
				roim = ro[1::2]
				gre = [2*np.pi*roshift[i]*(-rore[j]*d[j,i]-roim[j]*c[j,i]) \
						 for i in range(len(roshift)) for j in range(len(freq))] # g1N_re
				gre = np.sum(np.reshape(gre,(c.shape),order='F'),axis=0)
				#gre = np.reshape(gre,(c.shape),order='F')

				gim = [2*np.pi*roshift[i]*(rore[j]*c[j,i]-roim[j]*d[j,i]) \
						 for i in range(len(roshift)) for j in range(len(freq))] # g1N_re
				gim = np.sum(np.reshape(gim,(c.shape),order='F'),axis=0)
				#gre = np.reshape(gre,(c.shape),order='F')
			
				B[:len(gre),0] = gre
				B[len(gim):,0] = gim

				return B

			def y_from_Sh(S,B):# y contains the error terms delta_field, delta_ro 	

				return np.linalg.multi_dot((np.linalg.inv(np.dot(B.T,B)),B.T,S))

			def Sh_from_B_y(B,y):
	
				return np.dot(B,y)

			"""
			actual iteration starts here
			"""
			f = 0 # init fieldmap=0
			#start = time.time()
			for i in range(10):
				Sh = Sh_from_f(data1D,f,freq,roshift)
				ro = ro_from_Sh(Sh,A)
				#print('elapsed time 1 : '+str(time.time()-start))
				B = B_from_ro(ro,A,c,d,roshift,freq)
				y = y_from_Sh(Sh,B)
				#print('elapsed time 2 : '+str(time.time()-start))
				f = np.asarray(f + y[0]) # recalculate field
				#now = time.time()
				#print('elapsed time 3 : '+ str(now-start))
			#return (ro,y)
			#print('shapes before out : ro, y, f : ' +str(ro.shape)+' ; '+str(y.shape)+' ; '+str(f.shape))
			return np.concatenate([ro,y,np.atleast_1d(f)])
			#return ro

		A,c,d = make_Acd(self.roshift)
		#out = np.apply_along_axis(data,fit,axis=0)
		out = np.apply_along_axis(fit,0,self.data, self.roshift,A,c,d)
		print('out of applyalongaxin in d.ideal : '+str(out.shape))
		print(out[0,...].shape)
		print(out[1,...].shape)
		#return ro1_data, ro2_data
		ro = out[0:2*len(self.freq),...]
		y = out[2*len(self.freq):-1,...]
		f = out[-1,...]
		#print('shapes before out : ro, y, f : ' +str(ro.shape)+' ; '+str(y.shape)+' ; '+str(f.shape))
		return ro, y , f

if __name__ == '__main__':
	data, roshift = load_data()
	print('in data shape : '+str(data[0].shape))
	cut_data = []
	for item in data:
		cut_data.append(item[:,55:57,:,:]) 

	starttime = time.time()
	dix = dixon(cut_data, roshift, freq=[0,1400])
	ro, y, f = dix.ideal()
	print('elapsed time at main : '+str(time.time()-starttime))
	print('shapes ro, y, f : ' +str(ro.shape)+' ; '+str(y.shape)+' ; '+str(f.shape))
	print('dixon.ideal output shape : '+str(ro.shape)+' ; '+str(y.shape))
	abs_ro1 = np.absolute(np.vectorize(complex)(ro[0,...],ro[1,...]))
	abs_ro2 = np.absolute(np.vectorize(complex)(ro[2,...],ro[3,...]))
	print('abs_ro shape : '+str(abs_ro1.shape))
	# plotting stuff
	fig, axes = plt.subplots(4,1)
	plt.subplot(4,1,1)
	#ind 1 is the sliceindex
	plt.imshow(abs_ro1[0,0,:,:],cmap='gray')
	plt.subplot(4,1,2)
	plt.imshow(abs_ro2[0,0,:,:],cmap='gray')
	plt.subplot(4,1,3)
	plt.imshow(f[0,0,:,:],cmap='gray')
	plt.subplot(4,1,4)
	# ind 2 is the sliceindex ?
	plt.imshow(y[0,0,0,:,:])
	plt.show()
