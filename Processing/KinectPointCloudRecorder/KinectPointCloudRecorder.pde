// Daniel Shiffman
// Kinect Point Cloud example
// http://www.shiffman.net
// https://github.com/shiffman/libfreenect/tree/master/wrappers/java/processing

import org.openkinect.*;
import org.openkinect.processing.*;

import java.io.*;

// Kinect Library object
Kinect kinect;

float a = 0;

// Size of kinect image
int w = 640;
int h = 480;

// writing state indicator
boolean write = false;

// treshold filter initial value
int fltValue = 950;


// "recording" object. each vector element holds a coordinate map vector
ArrayList <Object> recording = new ArrayList<Object>(); 


// We'll use a lookup table so that we don't have to repeat the math over and over
float[] depthLookUp = new float[2048];

void setup() {
  size(800,600,P3D);
  kinect = new Kinect(this);
//  kinect.start();
  kinect.initDepth();
  // We don't need the grayscale image in this example
  // so this makes it more efficient
//  kinect.processDepthImage(false);

  // Lookup table for all possible depth values (0 - 2047)
  for (int i = 0; i < depthLookUp.length; i++) {
    depthLookUp[i] = rawDepthToMeters(i);
  }
  
}

void draw() {
  
  background(0);
  fill(255);
  textMode(SCREEN);
//  text("Kinect FR: " + (int)kinect.getDepthFPS() + "\nProcessing FR: " + (int)frameRate,10,16);

  // Get the raw depth as array of integers
  int[] depth = kinect.getRawDepth();

  // We're just going to calculate and draw every 4th pixel (equivalent of 160x120)
  int skip = 4;

  // Translate and rotate
  translate(width/2,height/2,-50);
  rotateY(a);

  //noStroke();
  //lights();
  
  
  int index = 0;

  
  PVector[] frame = new PVector[19200];
  
  stroke(255);
  for(int x=0; x<w; x+=skip) {
    for(int y=0; y<h; y+=skip) {
      int offset = x+y*w;

      // Convert kinect data to world xyz coordinate
      int rawDepth = depth[offset];
      
      boolean flt = true;
      PVector v = depthToWorld(x,y,rawDepth);
      if (flt && rawDepth > fltValue)
      {
        v = depthToWorld(x,y,2047);
      }

      frame[index] = v;
        
      index++;   

//      stroke(map(rawDepth,0,2048,0,256));
//      pushMatrix();
      // Scale up by 200
      float factor = 400;
//      translate(v.x*factor,v.y*factor,factor-v.z*factor);
      //sphere(1);
//      point(0,0);
point(v.x*factor,v.y*factor,factor-v.z*factor);
  
      //line (0,0,1,1);
//      popMatrix();
    }
  }
  
  if (write == true) {
    recording.add(frame);    

  }
  

  // Rotate
  //a += 0.015f;
}

// These functions come from: http://graphics.stanford.edu/~mdfisher/Kinect.html
float rawDepthToMeters(int depthValue) {
  if (depthValue < 2047) {
    return (float)(1.0 / ((double)(depthValue) * -0.0030711016 + 3.3309495161));
  }
  return 0.0f;
}

PVector depthToWorld(int x, int y, int depthValue) {

  final double fx_d = 1.0 / 5.9421434211923247e+02;
  final double fy_d = 1.0 / 5.9104053696870778e+02;
  final double cx_d = 3.3930780975300314e+02;
  final double cy_d = 2.4273913761751615e+02;

  PVector result = new PVector();
  double depth =  depthLookUp[depthValue];//rawDepthToMeters(depthValue);
  result.x = (float)((x - cx_d) * depth * fx_d);
  result.y = (float)((y - cy_d) * depth * fy_d);
  result.z = (float)(depth);
  return result;
}

void stop() {
//  kinect.quit();
  super.stop();
}


int currentFile = 0;

void saveFile() {

}

void keyPressed() { // Press a key to save the data

  if (key == '1')
  {
    fltValue += 50;
    println("fltValue: " + fltValue);
  }
  else if (key == '2')
  {
    fltValue -= 50;
    println("fltValue: " + fltValue);
  }
  else if (key=='4'){
    if (write == true) {
        write = false;
        
        println( "recorded " + recording.size() + " frames.");
        
        // saveFile();
        
        // save    
      
//      Enumeration e = recording.elements();
      
      println("Stopped Recording " + currentFile);
      for(int i=0; i<recording.size(); i++){
//      int i = 0;
//      while (e.hasMoreElements()) {
        
         // Create one directory
         boolean success = (new File("out"+currentFile)).mkdir(); 

        
        PrintWriter output = createWriter("out"+currentFile+"/frame" + i +".txt");
        PVector [] frame = (PVector []) recording.get(i); //nextElement();
        
        for (int j = 0; j < frame.length; j++) {
          if(frame[j].x * frame[j].y * frame[j].z != 0.0){
             output.println(j + ", " + frame[j].x + ", " + frame[j].y + ", " + frame[j].z );
          }
        }
        output.flush(); // Write the remaining data
        output.close();
      }
      currentFile++;
      
      
    
      }
  }
  else if (key == '3') {
        println("Started Recording "+currentFile);
        recording.clear();
        
        write = true;
  }

}

