<?
class Drink {
   var $id;
   var $ticks;
   var $volume;
   var $starttime;
   var $endtime;
   var $user_id;
   var $keg_id;
   var $status;

   function Drink($assoc) {
      $this->id = $assoc['id'];
      $this->ticks = $assoc['ticks'];
      $this->volume = $assoc['volume'];
      $this->starttime = $assoc['starttime'];
      $this->endtime = $assoc['endtime'];
      $this->user_id = $assoc['user_id'];
      $this->keg_id = $assoc['keg_id'];
      $this->status = $assoc['status'];
      $this->keg_obj = false;
      $this->drinker_obj = false;
      $this->grant_obj = false;
      $this->drink_size = 0;
      $this->username = "";
   }

   function inOunces() {
      return $this->keg_obj->toOunces($this->volume);
   }
   function getCalories() {
      return $this->keg_obj->toCalories($this->volume);
   }
   function convert_timestamp($timestamp, $adjust="") {
      $timestring = substr($timestamp,0,8)." ".
         substr($timestamp,8,2).":".
         substr($timestamp,10,2).":".
         substr($timestamp,12,2);
         return strtotime($timestring." $adjust");
   }
   function relDrinkTime() {
      $diff = mktime() - $this->convert_timestamp($this->endtime); 
      if ($diff < 60) { 
         $diff = round($diff);
         $res .= "$diff seconds ago";
      }
      elseif ($diff < 60*60) {
         $mins = sprintf("%i",$diff/60);
         $secs = $diff % 60;
         $res .= "$mins minutes $secs seconds ago";
      }
      elseif ($diff < 60*60*24) {
         $hours = intval($diff/(60*60));
         $mins = intval(($diff-$hours*60*60)/60);
         $res .= "$hours hours $mins minutes ago";
      }
      else {
         $res .= "on " . strftime("%A, %B %e, %Y - %H:%M", $stamp);
      }
      return $res;
   }
   function setUserName($name) {
      $this->username = $name;
   }
   function setKeg(&$keg) {
      $this->keg_obj = $keg;
   }
   function setDrinker(&$drinker) {
      $this->drinker_obj = $drinker;
   }
   function setGrant(&$grant) {
      $this->grant_obj = $grant;
   }

   function getCost() {
      return 0; // TODO FIXME
   }
   function setDrinkSize($size) {
      $this->drink_size = $size;
   }
   function infoURL() {
      //return "/drink-info.php?drink=" . $this->id;
      return "/drink/" . $this->id;
   }
   function getSize() {
      //return $this->drink_size;
      return $this->keg_obj->toOunces($this->volume);
   }
}

?>
