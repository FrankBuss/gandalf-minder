from sys import argv
from serial import Serial
import time
from time import sleep
from binascii import unhexlify, hexlify
from struct import pack, unpack
from avalonHashData import calculateAvalonHashData
from bitcoin import bitcoinConnect, getwork, submitWork, testNonce


# 32 bit word little-endian/big-endian conversion
def bytereverse(x):
	return unpack('>I', pack('<I', x))[0]

# low level serial port functions
def writeByte(byte):
	ser.write([byte])

def readByte():
	result = ser.read(1)
	if len(result) == 0:
		return -1
	else:
		return result[0]

# high level communication functions
def sendWord(word):
	#print('%08x' % word)
	for i in range(0, 8):
		writeByte(word & 0xf)
		word >>= 4

def sendWords(words):
	for word in words: sendWord(word)

def reset():
	writeByte(0x20)
	sleep(0.3)
	writeByte(0x21)
	sleep(0.3)

def setIdle():
	writeByte(0x10)

# config clock, hash data and start nonce
def configAsic(datastr):
	# clock config, comments copied from datasheet
	# with this config it runs at 250 MHz = 250 MH/s, 0.6 A on the 0.9 V supply
	r = 0
	f = 19
	od = 1
	clock = [
		1 << 0 |  # Bit[0]:Reserved, should be 1.
		1 << 1 |  # Bit[1]:clock  configuration  effect  bit,  if  this  bit  is  0,  all  clock  configuration at current transaction is ineffective.
		1 << 2 |  # Bit[2]:clock frequency effect bit, set to 1 if there are clock divider changes.
		0 << 3 |  # Bit[3]:clock gate, hash unit working clock will be gated it set to 1.
		1 << 4 |  # Bit[4]:clock will divided by 2 if set to 1
		0 << 5 |  # bit[5]:clock switch, hash unit working clock will switch to XCLKIN if set to 1.
		0 << 6 |  # Bit[6]:enable/disable core clock output to PAD, when set to 1, core clock output to PAD CORE_CLOCKOUT is disabled.
		0 << 7 |  # Bit[15:7]:Reserved, should be 0x00000
		r << 16 |  # bit[20:16] clock input divider R
		f << 21 |  # bit[27:21] clock feedback divider F
		od << 28  # bit[29:28] clock output divider OD
		, 0 ]
	# hash unit working clock frequency = XCLKIN frequency * (F+1)/((R+1)*(2^OD)).
	# F, R and OD configuration should satisfy the following three conditions:
	# 10MHz <= XCLKIN/(R+1) <= 50MHz
	# 500MHz <= XCLKIN*(F+1)/(R+1) <= 1000MHz
	# 62.5MHz <= XCLKIN*(F+1)/((R+1)*(2^OD)) <= 1000MHz
	sendWords(clock)

	# config hash data and start nonce
	startNonce = 0
	sendWords(calculateAvalonHashData(datastr))
	sendWord(startNonce)

def readWords(datastr, target):
	nonces = []
	while True:
		byte = 0
		word = 0
		end = time.time()
		if end - start > 17:
			return
		for i in range(32):
			bit = readByte()
			if bit >= 0:
				word >>= 1
				if bit: word |= 0x80000000
			else:
				break
		if word != 0:
			#print(end - start)
			nonce = bytereverse(word - 0x180)
			if nonce in nonces:
				# wrap around detection
				return
			else:
				nonces.append(nonce)
				print('nonce found: %08x' % (nonce))
				if testNonce(datastr, target, nonce):
					#print('data:', datastr)
					submitWork(datastr, nonce)


# evaluate command line arguments
if len(argv) != 4:
	print("usage: python %s username password server" % argv[0])
	exit(1)
username = argv[1]
password = argv[2]
server = argv[3]

# open serial port
ser = Serial(port='COM1', baudrate=115200, timeout=0.5)
print('Gandalf miner with Avalon chips')

# hold Avalon chip in reset until first work
setIdle()
writeByte(0x20)
setIdle()

# connect to pool
bitcoinConnect(username, password, server)

# getwork loop
while True:
	start = 0

	# clear receive buffer
	while ser.inWaiting(): readByte()

	# get new work
	(datastr, target) = getwork()
	print(time.asctime(), 'getwork')

	# reset chip
	setIdle()
	reset()
	
	# config chip
	configAsic(datastr)
	setIdle()
	start = time.time()

	# wait for nonce or timeout
	readWords(datastr, target)
