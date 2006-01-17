<?
   include_once('load-config.php');
   include_once('drinker.class.php');
   include_once('charge.class.php');
   include_once('Smarty.class.php');
   global $skin, $css;
   include_once('session.php');

   if ($_SESSION['skin']) {
      $skin = $_SESSION['skin'];
      $css  = $_SESSION['css'];
   }
   else {
      $skin = 'default';
      $css  = 'css.php?css=main.css';
   }

   class SmartyBeer extends Smarty {
      var $basedir;

      function SmartyBeer() {
         global $cfg, $skin, $css;
         // constructor
         $this->Smarty();

         $this->basedir = $cfg['dirs']['skindir'] . "/$skin";
         file_exists($this->basedir) || die("Skin dir {$this->basedir} not found!");
         $smartydir = $cfg['dirs']['smartytmp'] . "/$skin";
         file_exists($smartydir) || die("Smarty dir not found!");

         // smarty dirs
         $this->template_dir = $this->basedir . '/templates/';
         $this->config_dir = $this->basedir . '/configs/';
         $this->compile_dir = $smartydir . '/templates_c/';
         $this->cache_dir = $smartydir . '/cache/';
         $this->plugins_dir[] = '/var/www/localhost/htdocs/kegbotweb/src/includes/smarty_plugins';

         // default assignments
         $this->assign('app_name','kegbotweb');
         $this->assign('css',$css);
         $this->assign('skin',$skin);
         $this->assign('getvars', $_GET);
         ini_set('include_path', ini_get('include_path') . ':/var/www/localhost/htdocs/kegbotweb/src/includes/');

         // caching and related
         $this->caching = 0;
         $this->cache_lifetime = $cfg['smarty']['cachetime'];
         $this->compile_check = true;
      }

      function show_page($tpl, $cid="") {
         $this->display("misc/top.tpl", $cid);
         $this->display("pages/$tpl", $cid);
         $this->display("misc/bottom.tpl", $cid);
      }

   }

?>
