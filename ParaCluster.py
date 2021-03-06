#The idea here is to build a script which takes a list of fasta files (each file being a set of transcripts from a Corset cluster which supposedly come from the same gene).
#Then given each cluster, there should be a seperate parallelised job for each file which constructs the SuperTranscript for that cluster.

import multiprocessing, logging
from multiprocessing import Pool
from multiprocessing import Process
import os
from BuildSuperTranscript import SuperTran
import sys
import time
import argparse
from Checker import Checker

def worker(fname):
	seq =''
	ann = ''
	whirl_status=0
	try:
		seq,ann,whirl_status,transcript_status = SuperTran(fname)
	except:
		print("Failed:", fname)
	return seq,ann,whirl_status,transcript_status

#A little function to move all .fasta and .psl files created into a sub directory to tidy the space
def Clean(corsetfile):
	
	#First find the name of all the genes which files have been created for
	if(os.path.isfile(corsetfile)):
		#Make tidy directory
		dir = os.path.dirname(corsetfile)
		if(dir==''): dir='.'
		mcom = 'mkdir %s/InterFiles' %(dir)
		os.system(mcom)	
	

		print("Moving all fasta and psl files created to:")
		print("InterFiles/")
		clusters = []
		corse = open(corsetfile,'r')
		for line in corse:
			clust = line.split()[1].rstrip('/n')
			if(clust not in clusters): clusters.append(clust)
		
		#Now move all the fasta and psl files
		for clust in clusters: 
			mcom = 'mv %s/%s.fasta %s/InterFiles' %(dir,clust,dir)
			os.system(mcom)
			mcom = 'mv %s/%s.psl %s/InterFiles' %(dir,clust,dir)
			os.system(mcom)
	else:
		print("Not a real file, failed to clean")

#Split fasta file into genes first then parallelise the BLAT for the different genes
def Split(genome,corsetfile,ncore,maxTran):
	start_time = time.time()

	#Find working directory
	dir = os.path.dirname(corsetfile)
	if(dir==''): dir='.'


	#First create dictionary from corset output assigning a transcript to a cluster
	#Note: Corset throws away transcripts which don't have many read (> 10) to them
	#So we need to also ignore them

	cluster = {}
	if(os.path.isfile(corsetfile)):
		print("Creating dictionary of transcripts in clusters...")
		corse = open(corsetfile,'r')
		for line in corse:
			tran = line.split()[0]	
			clust = line.split()[1].rstrip('/n')
			#clust = clust.replace('/','-')
			cluster[tran] = clust			

	#Now loop through fasta file
	if(os.path.isfile(genome)):
		print("Creating a fasta file per gene...")
		#We only want to include transcripts deemed worthy by Corset

		#Parse Fasta file and split by gene
		fT = open(genome,'r')
		transcripts = {}
		geneid = {}
		transid ={}
		for line in fT:
			if(">" in line): #Name of
				tag = (line.split()[0]).lstrip('>')
				transcripts[tag] = ''
	
				#Assign names
				if(tag in cluster.keys()): geneid[tag] = cluster[tag] #If assigned by corset
				else: geneid[tag] = 'None'
				transid[tag] = tag
			else:
				transcripts[tag] = transcripts[tag] + line.split('\n')[0].split('\r')[0]	

		#Make a file for each gene
		gene_list = set(geneid.values())
		if('None' in gene_list): gene_list.remove('None') #Remove the placer holder for the ' None' which were transcripts not mapped to clusters in corset

		cnts = []
		for gene in gene_list:
			#Count number of transcripts assigned to cluster
			cnt=0
			for val in cluster.values():
				if(val ==gene):cnt=cnt+1				
			cnts.append(cnt)
			if(cnt > maxTran): print("WARNING: Ribbon will only take the first " + str(maxTran) +" transcripts since there are too many transcripts in cluster") 
		
			fn = dir + '/' + gene + '.fasta' #General		
			if(os.path.isfile(fn)): continue	#If already file
			

			f = open(fn,'w')
			ts=0 
			for tag in transcripts.keys():
				if(gene == geneid[tag]):
					if(ts==19): break #If already recorded 19 transcripts in gene.fasta file
					f.write('>' + tag +  '\n')
					f.write(transcripts[tag]+'\n')
					ts += 1
			f.close()

		#Now submit Build Super Transcript for each gene in parallel
		print("Now Building SuperTranscript for each gene...")
		jobs = []

		fnames = []
		for gene in gene_list:
			fname = dir + '/' + gene + '.fasta'
			fnames.append(fname)

		# BY POOL		
		#ncore = 4
		pool = Pool(processes=ncore)
		result = pool.map_async(worker,fnames)
		pool.close()
		pool.join()
		results = result.get()


		#Write Overall Super Duper Tran
		superf = open(dir + '/' +'SuperDuper.fasta','w')
		supgff = open(dir + '/' +'SuperDuper.gff','w')

		for i,clust in enumerate(fnames):
			#Just use the name of gene, without the preface
			fn = clust.split("/")[-1]
			fn = fn.split('.fasta')[0]
			#superf.write('>' + fn  + ' Number of transcripts: ' + str(cnts[i]) +  '\n')
			superf.write('>' + fn  + ' NoTrans:' + str(results[i][3]) + ',Whirls:' + str(results[i][2])  + '\n')
			#superf.write('>' + fn + '\n'  )
			superf.write(results[i][0] + '\n')

		#Write Super gff
		for res in results:
                        supgff.write(res[1])

		print("BUILT SUPERTRANSCRIPTS ---- %s seconds ----" %(time.time()-start_time))


	
if __name__ == '__main__':

	#Make argument parser
	parser = argparse.ArgumentParser()

	#Add Arguments
	parser.add_argument("GenomeFile",help="The name of the fasta file containing all transcripts")
	parser.add_argument("ClusterFile",help="The name of the text file with the transcript to cluster mapping")
	parser.add_argument("--cores",help="The number of cores you wish to run the job on (default = 1)",default=1,type=int)
	parser.add_argument("--alternate","-aa",help="Create alternate annotations and create metrics on success of SuperTranscript Building",action='store_true')
	parser.add_argument("--clear","-c",help="Clear intermediate files after processing",action='store_true')
	parser.add_argument("--maxTran",help="Set a maximum for the number of transcripts from a cluster to be included for building the SuperTranscript (default=50).",default=20,type=int)

	args= parser.parse_args()

	Split(args.GenomeFile,args.ClusterFile,args.cores,args.maxTran)

	if(args.alternate):
		dir = os.path.dirname(args.ClusterFile)
		if(dir==''): dir='.'
		print("Making Alternate Annotation and checks")
		Checker(dir+'/SuperDuper.fasta',args.cores)
		print('Done')

	if(args.clear):
		print("Clearing all extraneous files")
		Clean(args.ClusterFile)
		print("Done")
