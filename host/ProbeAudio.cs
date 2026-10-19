using System;
using System.Diagnostics;
using System.IO;
using UnityEngine;

namespace HollowCraft
{
    // Test capture reads the native listener mix without changing samples or recording other applications.
    internal sealed class ProbeAudio : MonoBehaviour
    {
        private readonly object gate=new object();
        private float[] samples;
        private int count,channels,rate;
        private bool overflow,channelsChanged;
        private double firstDsp,startedDsp;
        private double beganOffset;
        private long startedTicks;
        private string path;
        public void Begin(string directory,float probeStarted)
        {
            rate=AudioSettings.outputSampleRate;
            var buffer=new float[checked(rate*2*180)]; // ponytail: three minutes of stereo; stream PCM blocks if longer captures are needed. Overflow is reported.
            path=Path.Combine(directory,"audio.f32le");
            lock(gate)
            {
                samples=buffer;count=channels=0;overflow=channelsChanged=false;firstDsp=-1;
                startedDsp=AudioSettings.dspTime;startedTicks=Stopwatch.GetTimestamp();
                beganOffset=Time.realtimeSinceStartupAsDouble-probeStarted;
            }
        }
        private void OnAudioFilterRead(float[] data,int channelCount)
        {
            lock(gate)
            {
                if(samples==null) return;
                if(channels==0) { channels=channelCount;firstDsp=AudioSettings.dspTime; }
                if(channels!=channelCount) { channelsChanged=true;return; }
                if(data.Length>samples.Length-count) { overflow=true;return; }
                Array.Copy(data,0,samples,count,data.Length);count+=data.Length;
            }
        }
        public object Finish()
        {
            float[] buffer;int length,ch;bool clipped,changed;double offset;
            double elapsed=(Stopwatch.GetTimestamp()-startedTicks)/(double)Stopwatch.Frequency+beganOffset;
            lock(gate) { buffer=samples;samples=null;length=count;ch=channels;clipped=overflow;changed=channelsChanged;offset=firstDsp-startedDsp+beganOffset; }
            if(buffer==null) return null;
            string error=null;
            try
            {
                using(var file=new FileStream(path,FileMode.CreateNew,FileAccess.Write,FileShare.Read))
                {
                    var bytes=new byte[65536];
                    for(int at=0;at<length;)
                    { int n=Math.Min(bytes.Length/4,length-at);Buffer.BlockCopy(buffer,at*4,bytes,0,n*4);file.Write(bytes,0,n*4);at+=n; }
                }
            }
            catch(IOException exception) { error=exception.Message; }
            double duration=ch>0 ? length/(double)(ch*rate) : 0;
            return new {path,format="f32le",sampleRate=rate,channels=ch,samples=length,duration,
                startOffsetSeconds=offset,wallDuration=elapsed,timingErrorSeconds=offset+duration-elapsed,
                overflow=clipped,channelsChanged=changed,error};
        }
    }
}
