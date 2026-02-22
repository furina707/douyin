using System;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;

namespace LiveRecorderApp
{
    public class FFmpegService
    {
        private readonly string _ffmpegPath;

        public FFmpegService()
        {
            // 假设 ffmpeg.exe 在同一目录或系统路径
            _ffmpegPath = "ffmpeg.exe"; 
            if (!File.Exists(_ffmpegPath)) _ffmpegPath = @"c:\Users\cytFu\Desktop\douyin\ffmpeg.exe";
        }

        public void StartDownload(string url, string outputFile)
        {
            string dir = Path.GetDirectoryName(outputFile);
            if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);

            var startInfo = new ProcessStartInfo
            {
                FileName = _ffmpegPath,
                Arguments = $"-i \"{url}\" -c copy -y \"{outputFile}\"",
                CreateNoWindow = true,
                UseShellExecute = false,
                RedirectStandardError = true
            };

            Task.Run(() =>
            {
                using var process = Process.Start(startInfo);
                process.WaitForExit();
            });
        }

        public void Preview(string url)
        {
            string ffplay = Path.Combine(Path.GetDirectoryName(_ffmpegPath), "ffplay.exe");
            Process.Start(new ProcessStartInfo
            {
                FileName = ffplay,
                Arguments = $"-i \"{url}\" -window_title \"预览\"",
                CreateNoWindow = false,
                UseShellExecute = true
            });
        }
    }
}
