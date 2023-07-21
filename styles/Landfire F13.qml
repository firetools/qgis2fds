<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.12.2-București" styleCategories="AllStyleCategories" hasScaleBasedVisibilityFlag="0" maxScale="0" minScale="1e+08">
  <flags>
    <Identifiable>1</Identifiable>
    <Removable>1</Removable>
    <Searchable>0</Searchable>
  </flags>
  <customproperties>
    <property value="false" key="WMSBackgroundLayer"/>
    <property value="false" key="WMSPublishDataSourceUrl"/>
    <property value="0" key="embeddedWidgets/count"/>
    <property value="Value" key="identify/format"/>
  </customproperties>
  <pipe>
    <rasterrenderer type="paletted" band="1" opacity="1" alphaBand="-1" nodataColor="">
      <rasterTransparency/>
      <minMaxOrigin>
        <limits>None</limits>
        <extent>WholeRaster</extent>
        <statAccuracy>Estimated</statAccuracy>
        <cumulativeCutLower>0.02</cumulativeCutLower>
        <cumulativeCutUpper>0.98</cumulativeCutUpper>
        <stdDevFactor>2</stdDevFactor>
      </minMaxOrigin>
      <colorPalette>
        <paletteEntry value="0" color="#ffffff" alpha="255" label="NO_DATA"/>
        <paletteEntry value="1" color="#fffed4" alpha="255" label="FBFM01"/>
        <paletteEntry value="2" color="#fffd66" alpha="255" label="FBFM02"/>
        <paletteEntry value="3" color="#ecd463" alpha="255" label="FBFM03"/>
        <paletteEntry value="4" color="#fec177" alpha="255" label="FBFM04"/>
        <paletteEntry value="5" color="#f9c55c" alpha="255" label="FBFM05"/>
        <paletteEntry value="6" color="#d9c498" alpha="255" label="FBFM06"/>
        <paletteEntry value="7" color="#aa9b7f" alpha="255" label="FBFM07"/>
        <paletteEntry value="8" color="#e5fdd6" alpha="255" label="FBFM08"/>
        <paletteEntry value="9" color="#a2bf5a" alpha="255" label="FBFM09"/>
        <paletteEntry value="10" color="#729a55" alpha="255" label="FBFM10"/>
        <paletteEntry value="11" color="#ebd4fd" alpha="255" label="FBFM11"/>
        <paletteEntry value="12" color="#a3b1f3" alpha="255" label="FBFM12"/>
        <paletteEntry value="91" color="#ba7750" alpha="255" label="Urban"/>
        <paletteEntry value="92" color="#eaeaea" alpha="255" label="Snow/Ice"/>
        <paletteEntry value="93" color="#fdf2f2" alpha="255" label="Agriculture"/>
        <paletteEntry value="98" color="#89b7dd" alpha="255" label="Water"/>
        <paletteEntry value="99" color="#85999c" alpha="255" label="Barren"/>
      </colorPalette>
      <colorramp type="gradient" name="[source]">
        <prop v="215,25,28,255" k="color1"/>
        <prop v="43,131,186,255" k="color2"/>
        <prop v="0" k="discrete"/>
        <prop v="gradient" k="rampType"/>
        <prop v="0.25;253,174,97,255:0.5;255,255,191,255:0.75;171,221,164,255" k="stops"/>
      </colorramp>
    </rasterrenderer>
    <brightnesscontrast contrast="0" brightness="0"/>
    <huesaturation grayscaleMode="0" colorizeOn="0" colorizeStrength="100" colorizeRed="255" colorizeBlue="128" saturation="0" colorizeGreen="128"/>
    <rasterresampler zoomedInResampler="bilinear" maxOversampling="2"/>
  </pipe>
  <blendMode>0</blendMode>
</qgis>
