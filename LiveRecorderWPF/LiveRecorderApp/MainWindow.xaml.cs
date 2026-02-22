using System;
using System.Collections.ObjectModel;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;

namespace LiveRecorderApp
{
    public partial class MainWindow : Window
    {
        private ObservableCollection<MonitorItem> _items = new ObservableCollection<MonitorItem>();
        private DouyinClient _client = new DouyinClient();
        private FFmpegService _ffmpeg = new FFmpegService();
        private bool _isMonitoring = false;

        public MainWindow()
        {
            InitializeComponent();
            MonitorList.ItemsSource = _items;

            // 默认加入一个源并启动
            RoomIdInput.Text = "627921754944";
            AddMonitor_Click(null, null);
        }

        private void AddMonitor_Click(object sender, RoutedEventArgs e)
        {
            var input = RoomIdInput.Text.Trim();
            if (string.IsNullOrEmpty(input)) return;

            var id = ExtractRoomId(input);
            if (string.IsNullOrEmpty(id)) return;
            
            _items.Add(new MonitorItem 
            { 
                RoomId = id, 
                Platform = "Douyin", 
                DisplayName = id, 
                Status = "等待中...",
                StatusColor = "Gray",
                Title = "无",
                IsRecording = false
            });
            
            RoomIdInput.Clear();
        }

        private string ExtractRoomId(string input)
        {
            // 匹配 URL 中的抖音号
            var urlMatch = Regex.Match(input, @"(?:live\.douyin\.com/|follow/live/)(\d{8,15})");
            if (urlMatch.Success)
            {
                return urlMatch.Groups[1].Value;
            }
            
            // 如果只有数字
            if (Regex.IsMatch(input, @"^\d+$"))
            {
                return input;
            }

            return input;
        }

        private void StartAll_Click(object sender, RoutedEventArgs e)
        {
            if (!_isMonitoring)
            {
                _isMonitoring = true;
                StatusText.Text = "监控中";
                Task.Run(MonitorLoop);
            }
        }

        private async Task MonitorLoop()
        {
            while (_isMonitoring)
            {
                foreach (var item in _items)
                {
                    var status = await _client.GetStatusAsync(item.RoomId);
                    
                    Application.Current.Dispatcher.Invoke(() => {
                        item.Title = status.Title;
                        if (status.IsLive)
                        {
                            item.Status = "直播中";
                            item.StatusColor = "Green";
                            item.CurrentStreamUrl = status.StreamUrl;
                            item.DisplayName = status.Nickname;
                            if (!item.IsRecording)
                            {
                                item.IsRecording = true;
                                string file = $"Downloads/{item.DisplayName}_{DateTime.Now:yyyyMMdd_HHmmss}.mp4";
                                _ffmpeg.StartDownload(status.StreamUrl, file);
                            }
                        }
                        else
                        {
                            item.Status = "未开播";
                            item.StatusColor = "Red";
                            item.IsRecording = false; // Note: actual termination of ffmpeg process would be needed here
                        }
                    });
                }
                await Task.Delay(15000); // Check every 15s to avoid rate limiting
            }
        }

        private void Preview_Click(object sender, RoutedEventArgs e)
        {
            var btn = sender as Button;
            var item = btn?.DataContext as MonitorItem;
            if (item != null && !string.IsNullOrEmpty(item.CurrentStreamUrl))
            {
               _ffmpeg.Preview(item.CurrentStreamUrl);
            }
        }

        private void Stop_Click(object sender, RoutedEventArgs e)
        {
            var btn = sender as Button;
            var item = btn?.DataContext as MonitorItem;
            if (item != null)
            {
                _items.Remove(item);
            }
        }
    }
}