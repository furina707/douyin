using System.ComponentModel;

namespace LiveRecorderApp
{
    public class MonitorItem : INotifyPropertyChanged
    {
        public string RoomId { get; set; }
        public string Platform { get; set; }
        public string DisplayName { get; set; }
        
        private string _status;
        public string Status 
        { 
            get => _status; 
            set { _status = value; OnPropertyChanged(nameof(Status)); } 
        }

        private string _statusColor;
        public string StatusColor 
        { 
            get => _statusColor; 
            set { _statusColor = value; OnPropertyChanged(nameof(StatusColor)); } 
        }

        private string _title;
        public string Title 
        { 
            get => _title; 
            set { _title = value; OnPropertyChanged(nameof(Title)); } 
        }

        public string CurrentStreamUrl { get; set; }
        public bool IsRecording { get; set; }

        public event PropertyChangedEventHandler PropertyChanged;
        protected void OnPropertyChanged(string name) => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
    }
}
