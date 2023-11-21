#!/usr/bin/env python3
####################################
#  Marek Gorski, Dominika Switlik  #
####################################


# x_tr,y_tr= coo_trans(x,y,p_fr_x,p_fr_y)
# transformation:    x = p[0] + p[1] * x + p[2] * y + p[3] * x*y + p[4] * x*x + p[5] * y*y



#     EXAMPLE 1   (SIMPLE)
# sm=StarMatch()
# sm.ref_xr=x_ref
# sm.ref_yr=y_ref
# sm.ref_mr=m_ref
# sm.field_xr=x_field
# sm.field_yr=y_field
# sm.field_mr=m_field
# sm.go()
# print(sm.p_fr_x)      # field to reference
# print(sm.p_fr_y)
# print(sm.p_rf_x)      # reference to filed
# print(sm.p_rf_y)

#     EXAMPLE 2   (OTHER INSTRUMENTS)

# sm=StarMatch()
# sm.loud=True
# sm.nb_use=400
# sm.pixscale=0.3680           # HAWKI
# sm.fieldStarsRatio=0.58    # HAWKI
# sm.ref_xr=x_ref
# sm.ref_yr=y_ref
# sm.ref_mr=m_ref
# sm.field_xr=x_field
# sm.field_yr=y_field
# sm.field_mr=m_field
# sm.go()
# print(sm.mssg)
# print(sm.p_fr_x)
# print(sm.p_fr_y)
# print(sm.p_rf_x)
# print(sm.p_rf_y)
# sm.ref_match_x            - reference list with matched with feature recognition 
# sm.ref_match_y            - reference list with matched with feature recognition 
# sm.field_match_x          - field list with matched with feature recognition
# sm.field_match_y          - field list with matched with feature recognition
# sm.trainglesMatch_ref_x   - referece list with triangles match 
# sm.trainglesMatch_ref_y   - referece list with triangles match 
# sm.trainglesFail_ref_x    - reference list with traingles match fail
# sm.trainglesFail_ref_y    - reference list with traingles match fail



import sys, random
import numpy 


class StarMatch():
  def __init__(self):
    self.loud=False                   # print messege on terminal
    self.nb_use=200                   # number of stars included in feature matching
    self.nbPCent_match=0.25           # percentage of stars for which feature will be calulated
    self.nbStarsRadius=10             # average number of stars within the radius for local feature calculation
    self.fieldStarsRatio=1            # ratio of expected number of stars in field/reference. Exp: HAWKI(1CHIP)/SOFI = (3.75/4.9)**2 = 0.58
    self.pixscale=1                   # ratio of pixel scale field/reference. Exp: HAWKI/SOFI = 0.3680   
    self.starlist_error=0.05
    self.min_score=0.3
    
    self.mssg=""
    self.ref_xr=[]
    self.ref_yr=[]
    self.ref_mr=[]
    self.field_xr=[]
    self.field_yr=[]
    self.field_mr=[]

  def go(self):
      self.projectionMatch() 
      self.trianglesMatch()
      self.findtrans()


  def findtrans(self):
      if len(self.ref_xr)>10:
         # Field -> Ref
         x=numpy.array(self.trainglesMatch_ref_x)
         y=numpy.array(self.trainglesMatch_ref_y)       
         MX = numpy.array(list(zip(numpy.ones(len(x)),x,y,x*y,x*x,y*y)))

         MY = numpy.array(self.trainglesMatch_field_x)
         a,I,r = glsq(MX,MY)
         self.p_rf_x = numpy.array(a.getT())[0]

         MY = numpy.array(self.trainglesMatch_field_y)
         a,I,r = glsq(MX,MY)
         self.p_rf_y = numpy.array(a.getT())[0]


         # Ref -> Field
         x=numpy.array(self.trainglesMatch_field_x)
         y=numpy.array(self.trainglesMatch_field_y)       
         MX = numpy.array(list(zip(numpy.ones(len(x)),x,y,x*y,x*x,y*y)))
         MY = numpy.array(self.trainglesMatch_ref_x)
         a,I,r = glsq(MX,MY)
         self.p_fr_x = numpy.array(a.getT())[0]


         #MX = numpy.array(list(zip(numpy.ones(len(x)),x,y,x*y,x*x,y*y)))
         MY = numpy.array(self.trainglesMatch_ref_y)
         a,I,r = glsq(MX,MY)
         self.p_fr_y = numpy.array(a.getT())[0]



  def trianglesMatch(self):
    self.trainglesMatch_ref_x=[]
    self.trainglesMatch_ref_y=[]
    self.trainglesMatch_field_x=[]
    self.trainglesMatch_field_y=[]

    self.trainglesFail_ref_x=[]
    self.trainglesFail_ref_y=[]
    self.trainglesFail_field_x=[]
    self.trainglesFail_field_y=[]

    i_tab=list(range(len(self.ref_match_x)))
    for i,tmp in enumerate(self.ref_match_x):
        if len(i_tab)>2:
           i_tab.remove(i)
           i1=i
           i2,i3=random.sample(i_tab, 2)
           ax=[self.ref_match_x[i1],self.ref_match_x[i2],self.ref_match_x[i3]]
           ay=[self.ref_match_y[i1],self.ref_match_y[i2],self.ref_match_y[i3]]
           bx=[self.field_match_x[i1],self.field_match_x[i2],self.field_match_x[i3]]
           by=[self.field_match_y[i1],self.field_match_y[i2],self.field_match_y[i3]]
           error=0.01
           if triangleCompare(ax,ay,bx,by,error):  
              self.trainglesMatch_ref_x.append(self.ref_match_x[i1])
              self.trainglesMatch_ref_y.append(self.ref_match_y[i1])
              self.trainglesMatch_field_x.append(self.field_match_x[i1])
              self.trainglesMatch_field_y.append(self.field_match_y[i1])
           else: 
              self.trainglesFail_ref_x.append(self.ref_match_x[i1])
              self.trainglesFail_ref_y.append(self.ref_match_y[i1])
              self.trainglesFail_field_x.append(self.field_match_x[i1])
              self.trainglesFail_field_y.append(self.field_match_y[i1])     
     
    # sprawdzanie niedobitkow 
    i_tab=list(range(len(self.trainglesMatch_ref_x)))
    for i,tmp in enumerate(self.trainglesFail_ref_x):
        if len(i_tab)>2:
           i1=i
           i2,i3=random.sample(i_tab, 2)
           ax=[self.trainglesFail_ref_x[i1],self.trainglesMatch_ref_x[i2],self.trainglesMatch_ref_x[i3]]
           ay=[self.trainglesFail_ref_y[i1],self.trainglesMatch_ref_y[i2],self.trainglesMatch_ref_y[i3]]
           bx=[self.field_match_x[i1],self.trainglesMatch_field_x[i2],self.trainglesMatch_field_x[i3]]
           by=[self.field_match_y[i1],self.trainglesMatch_field_y[i2],self.trainglesMatch_field_y[i3]]
           error=0.01
           if triangleCompare(ax,ay,bx,by,error):  
              self.trainglesMatch_ref_x.append(self.trainglesFail_ref_x[i1])
              self.trainglesMatch_ref_y.append(self.trainglesFail_ref_y[i1])
              self.trainglesMatch_field_x.append(self.trainglesFail_field_x[i1])
              self.trainglesMatch_field_y.append(self.trainglesFail_field_y[i1])

    txt = "\nstars matched with triangles: " + str(len(self.trainglesMatch_ref_x))
    if self.loud: self.mssg=self.mssg+txt


  def projectionMatch(self):
    self.fieldStarsRatio=float(self.fieldStarsRatio)

    self.ref_mr,self.ref_xr,self.ref_yr=zip(*sorted(zip(self.ref_mr,self.ref_xr,self.ref_yr)))
    self.field_mr,self.field_xr,self.field_yr=zip(*sorted(zip(self.field_mr,self.field_xr,self.field_yr)))

    self.ref_mr=[float(x) for x in self.ref_mr]
    self.ref_xr=[float(x) for x in self.ref_xr]
    self.ref_yr=[float(x) for x in self.ref_yr]
    self.field_mr=[float(x) for x in self.field_mr]
    self.field_xr=[float(x) for x in self.field_xr]
    self.field_yr=[float(x) for x in self.field_yr]


    len_ref=len(self.ref_mr)
    len_field=len(self.field_mr)
    
    if len_ref>self.nb_use and len_field>self.nb_use*self.fieldStarsRatio:
       self.ref_m=self.ref_mr[:self.nb_use]
       self.ref_x=self.ref_xr[:self.nb_use]
       self.ref_y=self.ref_yr[:self.nb_use]
       self.field_m=self.field_mr[:int(self.nb_use*self.fieldStarsRatio)]
       self.field_x=self.field_xr[:int(self.nb_use*self.fieldStarsRatio)]
       self.field_y=self.field_yr[:int(self.nb_use*self.fieldStarsRatio)]       
    else:
       txt = "\n******* USING ALL STARS **********"
       lenstr=min(len_ref,len_field,len_field*self.fieldStarsRatio)
       if self.loud: self.mssg=self.mssg+txt
       
       self.ref_m=self.ref_mr[:lenstr]
       self.ref_x=self.ref_xr[:lenstr]
       self.ref_y=self.ref_yr[:lenstr]
       self.field_m=self.field_mr[:lenstr]
       self.field_x=self.field_xr[:lenstr]
       self.field_y=self.field_yr[:lenstr]   

    txt = "\nstars for local feature calculation (ref/field): " + str(len(self.ref_m)) + " / "+ str(len(self.field_m))
    if self.loud: self.mssg=self.mssg+txt

    ref_dx=max(self.ref_x)-min(self.ref_x)
    ref_dy=max(self.ref_y)-min(self.ref_y)
    field_dx=max(self.field_x)-min(self.field_x)
    field_dy=max(self.field_y)-min(self.field_y)    
    radius_ref=0.5*(self.nbStarsRadius/(float(len(self.ref_m))/float(ref_dx*ref_dy)))**0.5
    radius_field=radius_ref/self.pixscale
    txt = "\nradius for local feature match (ref/field): " + str(radius_ref) + " / "+ str(radius_field)
    if self.loud: self.mssg=self.mssg+txt

    self.ref_m=numpy.array(self.ref_m)
    self.ref_x=numpy.array(self.ref_x)
    self.ref_y=numpy.array(self.ref_y)

    self.field_m=numpy.array(self.field_m)
    self.field_x=numpy.array(self.field_x)
    self.field_y=numpy.array(self.field_y)

    if len(self.ref_m)*self.nbPCent_match>20 and len(self.field_m)*self.nbPCent_match>20:
       self.ref_star_m=self.ref_m[:int(len(self.ref_m)*self.nbPCent_match)]
       self.ref_star_x=self.ref_x[:int(len(self.ref_m)*self.nbPCent_match)]
       self.ref_star_y=self.ref_y[:int(len(self.ref_m)*self.nbPCent_match)]
       self.field_star_m=self.field_m[:int(len(self.field_m)*self.nbPCent_match)]
       self.field_star_x=self.field_x[:int(len(self.field_m)*self.nbPCent_match)]
       self.field_star_y=self.field_y[:int(len(self.field_m)*self.nbPCent_match)]    
    else:  
       print("\nALL IN ALL") 
       self.ref_star_m=self.ref_m
       self.ref_star_x=self.ref_x
       self.ref_star_y=self.ref_y
       self.field_star_m=self.field_m
       self.field_star_x=self.field_x
       self.field_star_y=self.field_y       

    txt = "\nstars for local feature match (ref/field): " + str(len(self.ref_star_m)) + " / "+ str(len(self.field_star_m))
    if self.loud: self.mssg=self.mssg+txt

    self.ref_star_K=[]

    for i,tmp in enumerate(self.ref_star_m):
        dist=(self.ref_star_x[i]-self.ref_x)**2+(self.ref_star_y[i]-self.ref_y)**2
        maska1=dist<(radius_ref)**2
        maska2=dist>0
        maska=[a and b for a,b in zip(maska1,maska2)]
        ref_dist=dist[maska]
        self.ref_ind_x=self.ref_x[maska]
        self.ref_ind_y=self.ref_y[maska]
        self.ref_ind_m=self.ref_m[maska]
        
        if len(self.ref_ind_m)==0: self.ref_star_K.append([[0],[0]])
        else:
           #direction = [(1,1),(1,0),(1,-1),(0,-1)]
           xx0=self.ref_star_x[i]-self.ref_ind_x[0]
           yy0=self.ref_star_y[i]-self.ref_ind_y[0]
           rr=(xx0**2+yy0**2)**0.5
           xx0=xx0/rr
           yy0=yy0/rr
           direction = [(xx0,yy0),(-1*yy0,xx0)]
           k = find_projection(self.ref_star_x[i]-self.ref_ind_x,self.ref_star_y[i]-self.ref_ind_y,direction,rr)
           k=[k[0][1:],k[1][1:]]
   
           self.ref_star_K.append(k)


    self.field_star_K=[]

    for i,tmp in enumerate(self.field_star_m):
        dist=(self.field_star_x[i]-self.field_x)**2+(self.field_star_y[i]-self.field_y)**2        
        maska1=dist<(radius_field)**2
        maska2=dist>0
        maska=[a and b for a,b in zip(maska1,maska2)]        
        field_dist=dist[maska]
        self.field_ind_x=self.field_x[maska]
        self.field_ind_y=self.field_y[maska]
        self.field_ind_m=self.field_m[maska]

        if len(self.field_ind_m)==0: self.field_star_K.append([[0],[0]])
        else:
           xx0=self.field_star_x[i]-self.field_ind_x[0]
           yy0=self.field_star_y[i]-self.field_ind_y[0]
           rr=(xx0**2+yy0**2)**0.5
           xx0=xx0/rr
           yy0=yy0/rr
           direction = [(xx0,yy0),(-1*yy0,xx0)]
           k = find_projection(self.field_star_x[i]-self.field_ind_x,self.field_star_y[i]-self.field_ind_y,direction,rr)
           k=[k[0][1:],k[1][1:]]
   
           self.field_star_K.append(k)
    
    self.succesRate_projection=0
    self.ref_match_x=[]
    self.ref_match_y=[]
    self.field_match_x=[]
    self.field_match_y=[]    
    for i,tmp in enumerate(self.ref_star_K): 
        s_max=0   
        j_match=0   
        for j,tmp in enumerate(self.field_star_K):
            s,d = check_starlist(self.ref_star_K[i],self.field_star_K[j],self.starlist_error)
            if s>s_max:
               s_max=s
               j_match=j
        if s_max>self.min_score:
           self.succesRate_projection=self.succesRate_projection+1
           self.ref_match_x.append(self.ref_star_x[i])
           self.ref_match_y.append(self.ref_star_y[i])  
           self.field_match_x.append(self.field_star_x[j_match])
           self.field_match_y.append(self.field_star_y[j_match])
    txt = "\nstars matched with local feature: "+str(self.succesRate_projection)
    if self.loud: self.mssg=self.mssg+txt



#---------------------------------------------------------------

def loadxytr(fname):
    with open(fname) as plik:
         for line in plik:
             if "reference=" in line: ref_file = line.split('reference=')[1].split()[0]
             if "field=" in line: field_file = line.split('field=')[1].split()[0]
             if "F2R Px=" in line: p_fr_x=numpy.array(line.split("=")[1].split()).astype(numpy.float)
             if "F2R Py=" in line: p_fr_y=numpy.array(line.split("=")[1].split()).astype(numpy.float)
             if "R2F Px=" in line: p_rf_x=numpy.array(line.split("=")[1].split()).astype(numpy.float)
             if "R2F Py=" in line: p_rf_y=numpy.array(line.split("=")[1].split()).astype(numpy.float)
         return(ref_file,field_file,p_fr_x,p_fr_y,p_rf_x,p_rf_y)    

def saveP2file(file_name_1,file_name_2,p_fr_x,p_fr_y,p_rf_x,p_rf_y):
    
    txt = "# reference="+file_name_1+" field="+file_name_2+"\n"
    txt = txt+"# x' = px[0] + px[1] * x + px[2] * y + px[3] * x*y + px[4] * x*x + px[5] * y*y\n"
    txt = txt+"# y' = py[0] + py[1] * x + py[2] * y + py[3] * x*y + py[4] * x*x + py[5] * y*y\n"
    txt = txt+"# Field to Reference\n"
    txt = txt+  "F2R Px=  " + "".join(str(tmp)+" " for tmp in p_fr_x)+"\n"
    txt = txt+  "F2R Py=  " + "".join(str(tmp)+" " for tmp in p_fr_y)+"\n"
    txt = txt+"# Reference to Field\n"
    txt = txt+  "R2F Px=  " + "".join(str(tmp)+" " for tmp in p_rf_x)+"\n"
    txt = txt+  "R2F Py=  " + "".join(str(tmp)+" " for tmp in p_rf_y)+"\n"   
    mch_file = file_name_2.split(".")[0]+".xytr"
    with open(mch_file, 'w') as f:
         f.write(txt)
    

def coo_trans(x,y,px,py):
    px=[float(p) for p in px]
    py=[float(p) for p in py]
    try: 
       x=float(x)
       y=float(y)
    except TypeError:   
       x=[float(f) for f in x]
       y=[float(f) for f in y]
       x=numpy.array(x)
       y=numpy.array(y)

    xt=px[0]+px[1]*x+px[2]*y+px[3]*x*y+px[4]*x*x+px[5]*y*y
    yt=py[0]+py[1]*x+py[2]*y+py[3]*x*y+py[4]*x*x+py[5]*y*y
    return xt,yt

def check_starlist(g1, g2,err):
    x1=g1[0]
    y1=g1[1]
    x2=g2[0]
    y2=g2[1]
    if len(x1)==0 or len(x2)==0: return 0,100
    if x1[0]==0 and x2[0]==0: return 1,100
    n_max = min(len(x1),len(x2))
    score=0
    diff = abs(sum(x1[:n_max])-sum(x2[:n_max]))+abs(sum(y1[:n_max])-sum(y2[:n_max]))
    for i in range(n_max):
        if abs(x1[i]-x2[i])<err and abs(y1[i]-y2[i])<err: score=score+(n_max-i)
        elif i<n_max-1 and abs(x1[i]-x2[i+1])<err and abs(y1[i]-y2[i+1])<err: score=score+(n_max-i)
        elif i>1 and abs(x1[i]-x2[i-1])<err and abs(y1[i]-y2[i-1])<err: score=score+(n_max-i)
    score=score/(0.5*n_max*(n_max+1))       
    return score,diff

def triangleCompare(ax,ay,bx,by,error):
    av1 = [ax[0]-ax[1],ay[0]-ay[1]]
    av2 = [ax[0]-ax[2],ay[0]-ay[2]]
    av3 = [ax[1]-ax[2],ay[1]-ay[2]]
    av1= av1 / numpy.linalg.norm(av1)
    av2= av2 / numpy.linalg.norm(av2)
    av3= av3 / numpy.linalg.norm(av3)
    DotP1,DotP2,DotP3 = numpy.dot(av1, av2),numpy.dot(av1, av3),numpy.dot(av2, av3)
    a_fi1 = numpy.arccos(DotP1)
    a_fi2 = numpy.arccos(DotP2)
    a_fi3 = numpy.arccos(DotP3)

    bv1 = [bx[0]-bx[1],by[0]-by[1]]
    bv2 = [bx[0]-bx[2],by[0]-by[2]]
    bv3 = [bx[1]-bx[2],by[1]-by[2]]
    if bv1 == [0,0] or bv2 == [0,0] or bv3 == [0,0]: return False  # bo na liscie field moga powtarzac sie gwiazdy
    bv1= bv1 / numpy.linalg.norm(bv1)
    bv2= bv2 / numpy.linalg.norm(bv2)
    bv3= bv3 / numpy.linalg.norm(bv3)
    DotP1,DotP2,DotP3 = numpy.dot(bv1, bv2),numpy.dot(bv1, bv3),numpy.dot(bv2, bv3)
    b_fi1 = numpy.arccos(DotP1)
    b_fi2 = numpy.arccos(DotP2)
    b_fi3 = numpy.arccos(DotP3)

    if abs(a_fi1-b_fi1)<error and abs(a_fi2-b_fi2)<error and abs(a_fi3-b_fi3)<error:
       return True
    else: return False   

        

def find_projection(x,y,direction,r):
    return numpy.array([(i[0]*x + i[1]*y)/r for i in direction])        


#wczytuje plik od lini
#dane=load_file(10,smc01.txt)
def load_file(min,file):
    f=open(file,'r')
    i=0
    dane=[]
    for line in f:
       if i>min-1 and line.strip()[0]!="#" and len(line.split())>0: dane.append(line.split())
       i=i+1
    dane=list(zip(*dane))   
    return dane	 


#wczytuje plik .ap
#dane,bledy=loadap(smc01.ap)
def loadap(file):
    f=open(file,'r')
    i=0
    dane=[]
    bledy=[]
    przelacznik=0
    for line in f:
       if i>2 and len(line.split())>0:
	       if przelacznik == 0:
	          dane.append(line.split())
	          przelacznik=1
	       elif przelacznik == 1:
	          bledy.append(line.split())
	          przelacznik=0
       i=i+1
    dane=list(zip(*dane))
    bledy=list(zip(*bledy))
    return dane, bledy

#wczytuje plik .out 
#dane=loadout(smc01.out)
def loadout(file):
    f=open(file,'r')
    i=0
    dane=[]
    for line in f:
       if i>2 and len(line.split())>0: dane.append(line.split())
       i=i+1
    dane=list(zip(*dane))
    return dane	 

def glsq(X,Y):
    #GLSQ 
    # a,I = glsq(X,Y)
    # Y - wektor dopasowania
    # X - macierz wartosci
    # a - wektor wspolczynnikow
    # I - macierz kowariancji
    X=numpy.matrix(X)
    Y=numpy.matrix(Y)  
    b=Y.getT()
    T=X.getT()
    TX=T*X
    I=TX.getI()
    a=I*T*b 
    r=numpy.array(Y)-numpy.squeeze(X*a)
    return a,I,r

def CooTrans(data,a1,a2,a3,a4,a5,a6):
    x1=numpy.array(data[0])
    x2=numpy.array(data[1])
    y = a1 + a2 * x1 + a3 * x2 + a4 * x1*x2 + a5 * x1**2 + a6 * x2**2
    return y

def CountDist(xr,yr):
    dist=[]
    xr=numpy.array(xr).astype(numpy.float)
    yr=numpy.array(yr).astype(numpy.float)
    for i,tmp in enumerate(xr):
        x=xr[i]
        y=yr[i]
        numpy.delete(xr,i)
        numpy.delete(yr,i)
        d=((x-xr)**2+(y-yr)**2)**0.5
        dist.extend(d)
    return(dist)  

